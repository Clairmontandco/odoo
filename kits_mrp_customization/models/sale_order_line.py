from odoo import models,api,fields,_
from odoo.exceptions import UserError, ValidationError
class sale_order_line(models.Model):
    _inherit='sale.order.line'

    delivery_date = fields.Date('Delivery Date',related='order_id.validity_date',store=True)
    product_category_id = fields.Many2one('product.category','Product Category',related='product_id.categ_id',store=True)
    product_tags_ids = fields.Many2many('x_product_tags','orderline_producttags_rel','order_line_id','x_product_tag_id','Product Tag',related='product_id.x_studio_many2many_field_bOjgj')
    kcash_product = fields.Boolean(string='K-Cash Product')   
    image_256 = fields.Binary(related='product_id.image_256')

    def unlink(self):
        if self.kcash_product :
            if self.price_unit == 0:
                return super(sale_order_line, self).unlink()
            else:
                raise UserError(_('Sorry you can not remove line with kcash reward.'))
        else:
            return super(sale_order_line, self).unlink()

    @api.depends('product_id')
    def _compute_product_updatable(self):
        for line in self:
            super(sale_order_line, line)._compute_product_updatable()
            if line.product_id.is_kcash_rewards:
                line.product_updatable = False
            else:
                line.product_updatable = True

    def _get_name_description(self):
        for rec in self:
            if rec.product_id.default_code:
                sku = '[' + rec.product_id.default_code + ']'
            product = rec.product_id.name.split(' ')
            product.append(sku) if sku else None
            product_sku = rec.name.split(' ')
            description = [element for element in product_sku if element not in product]
            return ' '.join(description)
