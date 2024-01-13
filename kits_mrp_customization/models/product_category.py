from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError, ValidationError

class ProductCategory(models.Model):
    _inherit = 'product.category'

    kits_route_ids = fields.Many2many('stock.location.route',string='Routes',domain="[('product_selectable','=',True)]")

    replenish_location_id = fields.Many2one('stock.location','Location')
    replenish_route_id = fields.Many2one('stock.location.route',string='Preferred Routes',domain="[('product_selectable','=',True)]")
    replenish_trigger = fields.Selection([('auto','Auto'),('manual','Manual')],default='auto',string='Trigger')
    replenish_product_min_qty = fields.Float('Min Quantity')
    replenish_product_max_qty = fields.Float('Max Quantity')
    replenish_qty_multiple = fields.Float('Multiple Quantity')

    putaway_location_in_id = fields.Many2one('stock.location','When Product arrives in')
    putaway_location_out_id = fields.Many2one('stock.location','Store to sublocation')

    def kits_action_update_route(self):
        for rec in self:
            related_products = self.env['product.product'].search([('categ_id','=',rec.id)])
            for product in related_products:
                product.route_ids = rec.kits_route_ids

    def kits_action_create_update_replanish(self):
        for rec in self:
            if not rec.replenish_location_id:
                raise UserError('Enter Location First !')
            related_products = self.env['product.product'].search([('categ_id','=',rec.id)])
            for product in related_products:
                existing_replanish = self.env['stock.warehouse.orderpoint'].search([('product_id','=',product.id),('location_id','=',rec.replenish_location_id.id)])
                if existing_replanish:
                    existing_replanish.write({
                        'route_id':rec.replenish_route_id.id,
                        'trigger':rec.replenish_trigger,
                        'product_min_qty':rec.replenish_product_min_qty,
                        'product_max_qty':rec.replenish_product_min_qty,
                        'qty_multiple':rec.replenish_qty_multiple
                    })
                else:
                    self.env['stock.warehouse.orderpoint'].create({
                        'product_id':product.id,
                        'location_id':rec.replenish_location_id.id,
                        'route_id':rec.replenish_route_id.id,
                        'trigger':rec.replenish_trigger,
                        'product_min_qty':rec.replenish_product_min_qty,
                        'product_max_qty':rec.replenish_product_min_qty,
                        'qty_multiple':rec.replenish_qty_multiple
                    })

    def kits_action_create_update_putaway_rules(self):
        for rec in self:
            if not rec.putaway_location_in_id:
                raise UserError('Enter - When Product arrives in - First !')
            if not rec.putaway_location_out_id:
                raise UserError('Enter - Store to sublocation - First !')
            related_products = self.env['product.product'].search([('categ_id','=',rec.id)])
            for product in related_products:
                putaway_replanish = self.env['stock.putaway.rule'].search([('product_id','=',product.id),('location_in_id','=',rec.putaway_location_in_id.id),('location_out_id','=',rec.putaway_location_out_id.id)])
                if not putaway_replanish:
                    self.env['stock.putaway.rule'].create({
                        'product_id':product.id,
                        'location_in_id':rec.putaway_location_in_id.id,
                        'location_out_id':rec.putaway_location_out_id.id,
                    })