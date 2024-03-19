from odoo import models,api,fields,_
from odoo.exceptions import UserError, ValidationError

class sale_order_line(models.Model):
    _inherit='sale.order.line'

    delivery_date = fields.Date('Delivery Date',related='order_id.validity_date',store=True)
    product_category_id = fields.Many2one('product.category','Product Category',related='product_id.categ_id',store=True)
    product_tags_ids = fields.Many2many('x_product_tags','orderline_producttags_rel','order_line_id','x_product_tag_id','Product Tag',related='product_id.x_studio_many2many_field_bOjgj')
    kcash_product = fields.Boolean(string='Clairmont Cash Product')   
    image_256 = fields.Binary(related='product_id.image_256')
    backorder_qty = fields.Float('BO Qty')
    order_line_id = fields.Many2one('sale.order.line','Original Line')

    def write(self, values):
        res = super(sale_order_line,self).write(values)
        for rec in self:
            if values.get('backorder_qty'):
                related_order_line = rec.order_id.sale_backorder_ids.order_line.filtered(lambda x:x.order_line_id == rec)    
                if related_order_line:
                    related_order_line.product_uom_qty = rec.backorder_qty         
        return res

    @api.ondelete(at_uninstall=False)
    def _unlink_except_confirmed(self):
        if self._check_line_unlink():
            picking_ids = self.order_id.picking_ids.filtered(lambda x:x.state != 'cancel')
            for picking in picking_ids:
                move_line = picking.move_ids_without_package.filtered(lambda x:x.sale_line_id == self)
                update_move_line = {'product_uom_qty':0,
                                    'quantity_done':0,
                                    'state':'cancel'}
                move_line.write(update_move_line)
                picking_state = picking.state
                picking.state = 'draft'
                move_line.unlink()
                picking.state = picking_state
                
    def unlink(self):
        for rec in self:
            if rec.kcash_product :
                if rec.price_unit == 0:
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
            sku = ""
            if rec.product_id.default_code:
                sku = '[' + rec.product_id.default_code + ']'
            product = rec.product_id.name.split(' ')
            product.append(sku) if sku else None
            new_line_description = rec.name.split('\n')
            new_line_description.pop(0)
            if new_line_description:
                description = new_line_description
            else:
                product_sku = rec.name.split(' ')
                description = [element for element in product_sku if element not in product]
            return ' '.join(description)