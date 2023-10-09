from odoo import models,api,fields,_

class sale_order_line(models.Model):
    _inherit='sale.order.line'

    delivery_date = fields.Date('Delivery Date',related='order_id.validity_date',store=True)
