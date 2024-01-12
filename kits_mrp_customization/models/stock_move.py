from odoo import _, api, fields, models, tools

class StockMove(models.Model):
    _inherit = 'stock.move'
    
    image_256 = fields.Binary(related='product_id.image_256')

class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'
    
    image_256 = fields.Binary(related='product_id.image_256')

class StockPutawayRule(models.Model):
    _inherit = 'stock.putaway.rule'

    def _enable_show_reserved(self):
        out_locations = self.location_out_id
        if out_locations:
            self.env['stock.picking.type'].with_context(active_test=False)\
                .search([('default_location_dest_id', 'in', out_locations.ids),('code','=','incoming')])\
                .write({'show_reserved': True})