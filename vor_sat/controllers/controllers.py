# # -*- coding: utf-8 -*-
# from odoo import http
# from odoo.addons.website.controllers.main import Website

# # class VorSimulador(http.Controller):
# #     @http.route('/vor_simulador/vor_simulador/', auth='public')
# #     def index(self, **kw):
# #         return "Hello, world"

# #     @http.route('/vor_simulador/vor_simulador/objects/', auth='public')
# #     def list(self, **kw):
# #         return http.request.render('vor_simulador.listing', {
# #             'root': '/vor_simulador/vor_simulador',
# #             'objects': http.request.env['vor_simulador.vor_simulador'].search([]),
# #         })

# #     @http.route('/vor_simulador/vor_simulador/objects/<model("vor_simulador.vor_simulador"):obj>/', auth='public')
# #     def object(self, obj, **kw):
# #         return http.request.render('vor_simulador.object', {
# #             'object': obj
# #         })
# class Website(Website):
#     @http.route(['/healthy'], type='http', auth="public", website=True)
#     def vor_heartbeat(self,**kw):


#         return ""