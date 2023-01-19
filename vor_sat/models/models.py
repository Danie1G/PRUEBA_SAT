# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import ValidationError
from datetime import datetime, timedelta, date
from cfdiclient import SolicitaDescarga, Fiel, Autenticacion, VerificaSolicitudDescarga, DescargaMasiva
import base64
from io import BytesIO
import zipfile
import logging
import xml.etree.ElementTree as ET
from xml.etree.ElementTree import Element, SubElement
_logger = logging.getLogger(__name__)


class VorSatSolicitud(models.Model):
    _name = 'vorsat.solicitud'
    _description = 'Solicitud de descarga'
    _order = 'id desc'
    _rec_name = 'id'

    token = fields.Char('Token')
    rfc_solicitante = fields.Char('RFC solicitante', required=True)
    fecha_inicial = fields.Date('Fecha inicial', default=date.today() - timedelta(days = 1), required=True)
    fecha_final = fields.Date('Fecha final', default=date.today(), required=True)
    rfc_emisor = fields.Char('RFC emisor')
    rfc_receptor = fields.Char('RFC receptor', required=True)

    id_solicitud = fields.Char('id_solicitud')
    cod_estatus = fields.Char('cod_estatus')
    mensaje = fields.Char('Mensaje')

    estado_solicitud = fields.Char('estado_solicitud')
    codigo_estado_solicitud = fields.Char('codigo_estado_solicitud')
    numero_cfdis = fields.Char('numero_cfdis')
    paquetes = fields.One2many('vorsat.paquete','solicitud','Paquetes')
    cfdis = fields.One2many('vorsat.cfdi', 'solicitud', 'CFDIs')

    estatus = fields.Selection([('1', 'Nueva'), ('2', 'Solicitar'), ('3', 'Verificar'),
                                ('4', 'Descargar'), ('5', 'Finalizado')],
                                'Estatus', default="1")

    @api.model
    def default_get(self, fields):
        res = super(VorSatSolicitud, self).default_get(fields)
        company = self.env.user.company_id
        res['rfc_solicitante'] = company.vat
        res['rfc_receptor'] = company.vat
        return res
    
    def regresar(self):
        for item in self:
            item.estatus = str(int(item.estatus) - 1) if int(item.estatus) > 1 else item.estatus


    def get_certificate(self):
        certificate_company = self.env.company.l10n_mx_edi_certificate_ids
        if certificate_company:
            return certificate_company[0]
        else:
            raise models.ValidationError('Primero debe proporcionar la FIEL en la configuración de la empresa')


    def get_token(self):
        certificate = self.get_certificate()
        FIEL_PAS = certificate.password
        cer_der = base64.b64decode(certificate.content)
        key_der = base64.b64decode(certificate.key)
        fiel = Fiel(cer_der, key_der, FIEL_PAS)
        auth = Autenticacion(fiel)
        return auth.obtener_token()

    def autenticar(self):
        self.token = self.get_token()

    def solicitar_descarga(self):
        certificate = self.get_certificate()
        FIEL_PAS = certificate.password
        cer_der = base64.b64decode(certificate.content)
        key_der = base64.b64decode(certificate.key)
        fiel = Fiel(cer_der, key_der, FIEL_PAS)
        descarga = SolicitaDescarga(fiel)
        result = descarga.solicitar_descarga(self.token, self.rfc_solicitante, self.fecha_inicial, self.fecha_final,
                                             rfc_emisor=self.rfc_emisor or '', rfc_receptor=self.rfc_receptor or '')
        _logger.error(result)

        self.id_solicitud = result.get('id_solicitud','')
        self.cod_estatus = result.get('cod_estatus','')
        self.mensaje = result.get('mensaje', '')
        # Validar cod_estatus si tiene error
        if self.cod_estatus == '5000':
            self.estatus = '3'
    
    def solicitar(self):
        self.autenticar()
        self.solicitar_descarga()

    def verificar_solicitud(self):
        certificate = self.get_certificate()
        FIEL_PAS = certificate.password
        cer_der = base64.b64decode(certificate.content)
        key_der = base64.b64decode(certificate.key)
        fiel = Fiel(cer_der, key_der, FIEL_PAS)
        v_descarga = VerificaSolicitudDescarga(fiel)
        result = v_descarga.verificar_descarga(self.token, self.rfc_solicitante, self.id_solicitud)
        self.cod_estatus = result.get('cod_estatus','')
        self.mensaje = result.get('mensaje', '')
        self.estado_solicitud = result.get('estado_solicitud', '')
        self.codigo_estado_solicitud = result.get('codigo_estado_solicitud', '')
        self.numero_cfdis = result.get('numero_cfdis', '')
        for paquete in result.get('paquetes', []):
            self.env['vorsat.paquete'].create({'id_paquete': paquete, 'solicitud': self.id})
        # Validar estado_solicitud si tiene error 'cod_estatus' != '5000'
        if self.estado_solicitud == '3' and self.codigo_estado_solicitud =='5000':
            self.estatus = '4'
        elif self.codigo_estado_solicitud == '5004':
            self.mensaje = 'No se encontró la solicitud'
    
    def verificar(self):
        self.autenticar()
        self.verificar_solicitud()
        if self.codigo_estado_solicitud == '5000':
            self.descargar_paquetes()

    def descargar_paquetes(self):
        certificate = self.get_certificate()
        FIEL_PAS = certificate.password
        cer_der = base64.b64decode(certificate.content)
        key_der = base64.b64decode(certificate.key)
        fiel = Fiel(cer_der, key_der, FIEL_PAS)
        descarga = DescargaMasiva(fiel)
        for paquete in self.paquetes:
            result = descarga.descargar_paquete(self.token, self.rfc_solicitante, paquete.id_paquete)
            # _logger.info(str(result))
            paquete.archivo = result.get('paquete_b64')
        self.descomprimir_paquete()
        self.extraer_info()
        self.estatus = '5'

    def descargar(self):
        self.autenticar()
        self.descargar_paquetes()
        
    def descomprimir_paquete(self):
        self.cfdis.unlink()
        for paquete in self.paquetes:
            archivo = base64.b64decode(paquete.archivo)
            zipdata = BytesIO()
            zipdata.write(archivo)
            myzipfile = zipfile.ZipFile(zipdata)        
            for item in myzipfile.filelist:
                with myzipfile.open(item.filename) as myfile:
                    self.env['vorsat.cfdi'].create(
                        {'solicitud': self.id,
                        'archivo': base64.b64encode(myfile.read()),
                        'filename': 'facturas.zip'
                        })

    def extraer_info(self):
        self.cfdis.extraer_info()

class VorSatPaquete(models.Model):
    _name = 'vorsat.paquete'
    _description = 'Paquete'
    id_paquete = fields.Char('id_paquete')
    solicitud = fields.Many2one('vorsat.solicitud', 'Solicitud', ondelete="cascade")
    archivo = fields.Binary("Archivo comprimido")

class VorSatCFDI(models.Model):
    _name = 'vorsat.cfdi'
    _description = 'CFDI'
    _order = 'fecha desc'
    _rec_name = 'tfd_uuid'


    solicitud = fields.Many2one('vorsat.solicitud', 'Solicitud')
    archivo = fields.Binary("Archivo")
    filename = fields.Char("Nombre del archivo")

    version = fields.Char("Versión")
    folio = fields.Char("Folio")
    fecha = fields.Date("Fecha")
    sello = fields.Char("Sello")
    forma_pago = fields.Char("Forma Pago")
    no_certificado = fields.Char("Número Certificado")
    certificado = fields.Char("Certificado")
    sub_total = fields.Float("Subtotal")
    moneda = fields.Char("Moneda")
    total = fields.Float("Total")
    tipo_de_comprobante = fields.Char("Tipo de Comprobante")
    metodo_pago = fields.Char("Método de Pago")
    lugar_expedicion = fields.Char("Lugar de expedición")

    emisor = fields.Many2one('res.partner', 'Emisor')
    emisor_rfc = fields.Char("Emisor RFC")
    emisor_nombre = fields.Char("Emisor Nombre")
    emisor_regimen_fiscal = fields.Char("Emisor Regimen fiscal")

    receptor = fields.Many2one('res.company', 'Receptor')
    receptor_rfc = fields.Char("Receptor RFC")
    receptor_nombre = fields.Char("Receptor Nombre")
    receptor_uso_CFDI = fields.Char("Receptor UsoCFDI")

    total_impuestos_trasladados = fields.Char("Total Impuestos Trasladados")
    
    conceptos = fields.One2many('vorsat.concepto', 'cfdi', 'Conceptos')

    tfd_version = fields.Char("Versión")
    tfd_uuid = fields.Char("UUID")
    tfd_fecha_timbrado = fields.Date('Fecha timbrado')
    tfd_sello_cfd = fields.Char("Sello CFD")
    tfd_no_certificado_sat = fields.Char("Número certificado SAT")
    tfd_sello_sat = fields.Char("Sello SAT")
    tfd_rfc_prov_certif = fields.Char("RfcProvCertif")

    exportada = fields.Boolean('Exportada')
    descartado = fields.Boolean('Descartado')
    estatus = fields.Selection([('1','Nueva'),('2','Completa'),('3','Exportada'),('d','Descartada')],store=True, compute="get_estatus", string='Estatus')

    def get_estatus(self):
        for item in self:
            if item.exportada:
                item.estatus = '3'
            if item.descartado:
                item.estatus = 'd'
            else:
                completa = True
                for concepto in item.conceptos:
                    if not concepto.producto:
                        completa = False
                if not item.emisor:
                    completa = False
                if not item.receptor:
                    completa = False
                if completa:
                    item.estatus = '2'
                else:
                    item.estatus = '1'

    def descartar(self):
        for item in self:
            item.write({'descartado':True})

    def procesar(self):
        for item in self:
            account_move_dict = { 
                'ref': item.tfd_uuid,
                'invoice_date': item.fecha,
                'date': item.fecha,
                'type': 'in_invoice',
                'partner_id': item.emisor.id,
                # 'commercial_partner_id':item.emisor.id,
                'company_id': item.receptor.id,
                'invoice_line_ids': [], 
            }
            last_account_move = self.env['account.move'].search([('partner_id', '=', item.emisor.id), ('type','=','in_invoice')], order='date desc', limit=1)
            if last_account_move:
                account_move_dict['invoice_payment_term_id'] = last_account_move.invoice_payment_term_id.id


            for concepto in item.conceptos:
                account_move_dict['invoice_line_ids'].append(
                      (0, 0, {
                    'product_id': concepto.producto.id,
                    'quantity': concepto.cantidad,
                    'price_unit': concepto.valor_unitario,
                    'credit': concepto.importe,
                })
                )
            account_move = self.env['account.move'].create(account_move_dict)
            account_move.partner_id = item.emisor.id,
            item.exportada = True
            context = dict(self.env.context)
            context['form_view_initial_mode'] = 'edit'
            return {
            'name': 'Factura CFDI',
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'views': [[False, 'form']],
            'res_id': account_move.id,
            'context': context,
        }
            
    def extraer_info(self):
        uri = '{http://www.sat.gob.mx/cfd/3}'
        tfd = '{http://www.sat.gob.mx/TimbreFiscalDigital}'
        for item in self:
            try:
                decoded_xml = base64.b64decode(item.archivo)
                string_xml = decoded_xml.decode('utf-8')
                tree = ET.fromstring(string_xml)

                item.version = tree.get('Version')
                item.folio = tree.get('Folio')
                item.fecha = tree.get('Fecha')
                item.sello = tree.get('Sello')
                item.forma_pago = tree.get('FormaPago')
                item.no_certificado = tree.get('NoCertificado')
                item.certificado = tree.get('Certificado')
                item.sub_total = tree.get('SubTotal')
                item.moneda = tree.get('Moneda')
                item.total = tree.get('Total')
                item.tipo_de_comprobante = tree.get('TipoDeComprobante')
                item.metodo_pago = tree.get('MetodoPago')
                item.lugar_expedicion = tree.get('LugarExpedicion')

                emisor = tree.find(uri + 'Emisor')
                if emisor is not None:
                    partner = self.env['res.partner'].search([('vat','=',emisor.get('Rfc',''))], limit=1)
                    if partner:
                        item.emisor = partner
                    item.emisor_rfc = emisor.get('Rfc')
                    item.emisor_nombre = emisor.get('Nombre')
                    item.emisor_regimen_fiscal = emisor.get('RegimenFiscal')

                receptor = tree.find(uri + 'Receptor')
                if receptor is not None:
                    partner = self.env['res.company'].search(['|',('vat','=',receptor.get('Rfc','')), ('rfc','=',receptor.get('Rfc',''))], limit=1)
                    if partner:
                        item.receptor = partner
                    item.receptor_rfc = receptor.get('Rfc')
                    item.receptor_nombre = receptor.get('Nombre')
                    item.receptor_uso_CFDI = receptor.get('UsoCFDI')
                
                impuestos = tree.find(uri + 'Impuestos')
                if impuestos is not None:
                    item.total_impuestos_trasladados = impuestos.get('TotalImpuestosTrasladados')

                timbre = tree.find(uri + 'Complemento/' + tfd + 'TimbreFiscalDigital')
                if timbre is not None:
                    item.tfd_version = timbre.get('Version')
                    item.tfd_uuid = timbre.get('UUID')
                    item.tfd_fecha_timbrado = timbre.get('FechaTimbrado')
                    item.tfd_sello_cfd = timbre.get('SelloCFD')
                    item.tfd_no_certificado_sat = timbre.get('NoCertificadoSAT')
                    item.tfd_sello_sat = timbre.get('SelloSAT')
                    item.tfd_rfc_prov_certif = timbre.get('RfcProvCertif')

                conceptos = tree.findall(uri + 'Conceptos/' + uri + 'Concepto')
                if conceptos:
                    item.conceptos.unlink()
                    for concepto in conceptos:
                        self.env['vorsat.concepto'].create({
                            'cfdi': item.id,
                            'clave_unidad': concepto.get('ClaveUnidad'),
                            'clave_prod_serv': concepto.get('ClaveProdServ'),
                            'no_identificacion': concepto.get('NoIdentificacion'),
                            'cantidad': concepto.get('Cantidad'),
                            'unidad': concepto.get('Unidad'),
                            'descripcion': concepto.get('Descripcion'),
                            'valor_unitario': concepto.get('ValorUnitario'),
                            'importe': concepto.get('Importe'),
                        })
                
            except:
                _logger.info('Error en extraer_info CFDI')

class VorSatConcepto(models.Model):
    _name = 'vorsat.concepto'
    _description = 'Concepto'

    cfdi = fields.Many2one('vorsat.cfdi', 'CFDI', ondelete="cascade")
    producto = fields.Many2one('product.product', 'Producto')
    clave_unidad = fields.Char("Clave unidad")
    clave_prod_serv = fields.Char("Clave producto servicio")
    no_identificacion = fields.Char("Número identificación")
    cantidad = fields.Float("Cantidad")
    unidad = fields.Char("Unidad")
    descripcion = fields.Char("Descripción")
    valor_unitario = fields.Float("Valor unitario")
    importe = fields.Float("Importe")

    emisor_rfc = fields.Char("Emisor RFC", related="cfdi.emisor_rfc")
    fecha = fields.Date('Fecha timbrado', related="cfdi.fecha")

    @api.model
    def create(self, values):
        concepto = super(VorSatConcepto, self).create(values)
        if not concepto.producto:
            concepto_similar = self.env['vorsat.concepto'].search([('clave_prod_serv','=',concepto.clave_prod_serv),
                                                            ('emisor_rfc', '=', concepto.emisor_rfc),
                                                            ('producto', '!=', False),
                                                            ], order='fecha desc', limit=1)
            if concepto_similar:
                concepto.producto = concepto_similar.producto.id
        return concepto
