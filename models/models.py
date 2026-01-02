# -*- coding: utf-8 -*-

# from odoo import models, fields, api


# class xam_product_supersede(models.Model):
#     _name = 'xam_product_supersede.xam_product_supersede'
#     _description = 'xam_product_supersede.xam_product_supersede'

#     name = fields.Char()
#     value = fields.Integer()
#     value2 = fields.Float(compute="_value_pc", store=True)
#     description = fields.Text()
#
#     @api.depends('value')
#     def _value_pc(self):
#         for record in self:
#             record.value2 = float(record.value) / 100

