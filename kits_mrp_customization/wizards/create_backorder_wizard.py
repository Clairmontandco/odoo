from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError, ValidationError

class CreateBackorderLine(models.TransientModel):
    _name = 'create.backorder.line'

    wiz_id = fields.Many2one('create.backorder.wizard','Wizard')
    order_line_id = fields.Many2one('sale.order.line','Order Line')
    product_id = fields.Many2one('product.product','Product')
    product_uom_qty = fields.Float('Quantity')

class CreateBackorderWizard(models.TransientModel):
    _name = 'create.backorder.wizard'

    order_id = fields.Many2one('sale.order','Order')
    backorder_line_ids = fields.One2many('create.backorder.line','wiz_id','Order Line')

    def action_process(self):
        sale_order_lines = []
        if self.order_id.picking_ids.filtered(lambda x:x.state in ('assigned','done')):
            raise UserError('You can not create backorder after order have invoice and delivery is in done.')
        for line in self.backorder_line_ids:
            order_line_id = line.order_line_id 
            if order_line_id:
                onhand_qty = line.product_id.qty_available
                reorder_qty = line.product_uom_qty
                order_line_id.product_uom_qty = onhand_qty
                order_line_id.backorder_qty = reorder_qty
                price_unit = order_line_id.price_unit 
                sale_order_line_vals = {
                    'product_id': line.product_id.id,
                    'product_uom_qty': reorder_qty,
                    'price_unit': price_unit,
                    'order_line_id':order_line_id.id }
                sale_order_lines.append((0, 0, sale_order_line_vals))
            elif not order_line_id:
                price_unit = line.product_id.product_tmpl_id.list_price
                sale_order_line_vals = {
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.product_uom_qty,
                    'price_unit': price_unit}
                sale_order_lines.append((0, 0, sale_order_line_vals))
        if sale_order_lines:
            sale_order_vals = {
                    'partner_id': self.order_id.partner_id.id,
                    'parent_order_id' : self.order_id.id,
                    'order_line': sale_order_lines,
                    'payment_term_id':self.order_id.payment_term_id.id,
                    'validity_date':self.order_id.validity_date,
                    }
            sale_order = self.env['sale.order'].create(sale_order_vals)
            sale_order.name = sale_order.name.replace('SO','BO')
        if self.order_id.state in ('sale','done'):
            sale_order.action_confirm()
            delivery = sale_order.picking_ids.filtered(lambda x:x.state not in ('cancel'))
            parent_delivery = self.order_id.picking_ids.filtered(lambda x:x.state not in ('cancel') and not x.backorder_id )
            delivery.backorder_id = parent_delivery[0] if parent_delivery else None