# -*- coding: utf-8 -*-
{
    'name': "Descarga SAT CFDI",
    'version': '1.0',
  "summary"              :  """ Descarga de CFDI del portal del SAT """,
    'description': """
        Contabilizar facturas de Proveedores nunca ha sido tan fácil. Con este módulo podrás descargar los CFDI's del portal del sat y contabilizar las facturas en el sistema.
    """,
  'author': 'Centricital',
  'depends': ['base', 'product','account'],
  "installable": True,
  "currency"             :  "USD",
  "images"               :  ['static/description/banner.png'],
  'data': [
      'security/ir.model.access.csv',
      'views/views.xml',
      # 'views/ext_company_sat.xml',
      'views/templates.xml',
      'data/scheduled_actions.xml'
  ],
  'external_dependencies': {"python": [
      'cfdiclient',
      'zipfile'
  ]},
  "application"          :  True,
  "price"                :  0,
}
