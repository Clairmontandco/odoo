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

    include_subcategory = fields.Boolean('Include Subcategory')

    bom_id = fields.Many2one('mrp.bom','BOM')

    def kits_action_update_route(self):
        for rec in self:
            domain = [('categ_id','child_of',rec.id)] if rec.include_subcategory else [('categ_id','=',rec.id)]
            related_products = self.env['product.product'].search(domain)
            for product in related_products:
                product.route_ids = rec.kits_route_ids

    def kits_action_create_update_replanish(self):
        for rec in self:
            if not rec.replenish_location_id:
                raise UserError('Enter Location First !')
            domain = [('categ_id','child_of',rec.id)] if rec.include_subcategory else [('categ_id','=',rec.id)]
            related_products = self.env['product.product'].search(domain)
            for product in related_products:
                if not self.env['mrp.bom'].search(['|', ('product_id', 'in', product.ids),
                                            '&', ('product_id', '=', False), ('product_tmpl_id', 'in', product.product_tmpl_id.ids),
                                       ('type', '=', 'phantom')], count=True):
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
            domain = [('categ_id','child_of',rec.id)] if rec.include_subcategory else [('categ_id','=',rec.id)]
            related_products = self.env['product.product'].search(domain)
            for product in related_products:
                putaway_replanish = self.env['stock.putaway.rule'].search([('product_id','=',product.id),('location_in_id','=',rec.putaway_location_in_id.id),('location_out_id','=',rec.putaway_location_out_id.id)])
                if not putaway_replanish:
                    self.env['stock.putaway.rule'].create({
                        'product_id':product.id,
                        'location_in_id':rec.putaway_location_in_id.id,
                        'location_out_id':rec.putaway_location_out_id.id,
                    })

    def action_create_bom(self):
        for rec in self:
            if not rec.bom_id:
                raise UserError('Enter BOM First !')
            domain = [('categ_id','child_of',rec.id),('detailed_type','=','product')] if rec.include_subcategory else [('categ_id','=',rec.id),('detailed_type','=','product')]
            related_product_tmpl = self.env['product.template'].search(domain)
            for product_tmpl in related_product_tmpl:
                mrp_bom = self.env['mrp.bom'].search([('product_tmpl_id','=',product_tmpl.id),('id','!=',rec.bom_id.id)])
                if not mrp_bom:
                    bom = rec.bom_id.copy()
                    bom.write({'product_tmpl_id':product_tmpl.id})
                    bom.onchange_product_tmpl_id()
                else:
                    for bom in mrp_bom:
                        bom_details = rec.bom_id.read()
                        product_tmpl_id = bom.product_tmpl_id.id
                        bom.bom_line_ids.unlink()
                        bom.operation_ids.unlink()
                        for bom_line in rec.bom_id.bom_line_ids:
                            bom_line.copy({'bom_id':bom.id}).id
                        for op_line in rec.bom_id.operation_ids:
                            op_line.copy({'bom_id':bom.id}).id
                        bom_details[0].pop('message_follower_ids')
                        bom_details[0].pop('bom_line_ids')
                        bom_details[0].pop('operation_ids')
                        bom.write(bom_details[0])
                        bom.write({'product_tmpl_id':product_tmpl_id})
                        bom.onchange_product_tmpl_id()
