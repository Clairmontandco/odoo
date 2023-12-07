from odoo import fields, models, _


class StockMove(models.Model):
    _inherit = "stock.move"

    def _get_new_picking_values(self):
        res = super(StockMove, self)._get_new_picking_values()
        order_id = self.sale_line_id.order_id
        if order_id.mk_id:
            res.update({'mk_instance_id': order_id.mk_instance_id.id})
            if order_id.updated_in_marketplace:
                res.update({'updated_in_marketplace': True})
        return res

    def _assign_picking_post_process(self, new=False):
        res = super(StockMove, self)._assign_picking_post_process(new=new)
        if new and self.env.context.get('create_date', False):
            order_id = self.sale_line_id.order_id
            if order_id.mk_id:
                picking_id = self.mapped('picking_id')
                picking_id.scheduled_date = self.env.context.get('create_date')
        return res

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    updated_in_marketplace = fields.Boolean("Updated in Marketplace?", default=False, copy=False)
    cancel_in_marketplace = fields.Boolean("Cancel in Marketplace", default=False, copy=False)
    mk_instance_id = fields.Many2one('mk.instance', "Marketplace Instance", ondelete='cascade', copy=False)
    marketplace = fields.Selection(related="mk_instance_id.marketplace", string='Marketplace')
    no_of_retry_count = fields.Integer(string="Retry Count", help="No of count that queue went in process.", compute_sudo=True)
    is_marketplace_exception = fields.Boolean(string="Marketplace Exception?", copy=False, help="Technical field to filter out problematic records from update order status process.")
    exception_message = fields.Text(string="Marketplace Exception Message", copy=False)
    is_fbm_order = fields.Boolean(string="Is Fulfillment By Marketplace Order?", copy=False)

    def update_order_status_to_marketplace(self):
        """
        Calling hook type method to update order status. Just need to add hook type method in individual marketplace app.
        :return: True
        """
        if hasattr(self, '%s_update_order_status_to_marketplace' % self.mk_instance_id.marketplace):
            getattr(self, '%s_update_order_status_to_marketplace' % self.mk_instance_id.marketplace)()
        return True

    def do_marked_as_updated_in_odoo(self):
        self.ensure_one()
        self.updated_in_marketplace = True
        self.is_marketplace_exception = False


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    def create_or_update_inventory_quant(self, location_id, product_id, quantity, name="", auto_validate=False):
        inventory_quant = self.search([('location_id', '=', location_id), ('product_id', '=', product_id.id)])
        if inventory_quant:
            inventory_quant.write({'inventory_quantity': quantity})
        else:
            inventory_quant = self.with_context(inventory_mode=True).create({'product_id': product_id.id, 'location_id': location_id, 'inventory_quantity': quantity})
        if auto_validate and product_id.tracking not in ['lot', 'serial']:
            inventory_quant.with_context(inventory_name=name).action_apply_inventory()
        return inventory_quant
