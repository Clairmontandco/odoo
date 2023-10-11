from odoo import models,api,fields,_

class sale_order_line(models.Model):
    _inherit='sale.order.line'

    delivery_date = fields.Date('Delivery Date',related='order_id.validity_date',store=True)
    product_category_id = fields.Many2one('product.category','Product Category',related='product_id.categ_id',store=True)
    product_tags_ids = fields.Many2many('x_product_tags','orderline_producttags_rel','order_line_id','x_product_tag_id','Product Tag',related='product_id.x_studio_many2many_field_bOjgj')
