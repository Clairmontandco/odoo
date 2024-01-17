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

    product_qty = fields.Float('Quantity')
    bom_type = fields.Selection([('normal','Manufacturing this product'),('phantom','Kit')],default='normal',string='BoM Type')
    bom_category_line_ids = fields.One2many('bom.category.line','categ_id','BOM Category Line')

    def kits_action_update_route(self):
        category = self.env['product.category'].search([('id', 'child_of', self.id)]) if self.include_subcategory else self
        for rec in category:
            related_products = self.env['product.product'].search([('categ_id','=',rec.id)])
            for product in related_products:
                product.route_ids = self.kits_route_ids

    def kits_action_create_update_replanish(self):
        category = self.env['product.category'].search([('id', 'child_of', self.id)]) if self.include_subcategory else self
        for rec in category:
            if not self.replenish_location_id:
                raise UserError('Enter Location First !')
            related_products = self.env['product.product'].search([('categ_id','=',rec.id)])
            for product in related_products:
                if not self.env['mrp.bom'].search(['|', ('product_id', 'in', product.ids),
                                            '&', ('product_id', '=', False), ('product_tmpl_id', 'in', product.product_tmpl_id.ids),
                                       ('type', '=', 'phantom')], count=True):
                    existing_replanish = self.env['stock.warehouse.orderpoint'].search([('product_id','=',product.id),('location_id','=',self.replenish_location_id.id)])
                    if existing_replanish:
                        existing_replanish.write({
                            'route_id':self.replenish_route_id.id,
                            'trigger':self.replenish_trigger,
                            'product_min_qty':self.replenish_product_min_qty,
                            'product_max_qty':self.replenish_product_min_qty,
                            'qty_multiple':self.replenish_qty_multiple
                        })
                    else:
                        self.env['stock.warehouse.orderpoint'].create({
                            'product_id':product.id,
                            'location_id':self.replenish_location_id.id,
                            'route_id':self.replenish_route_id.id,
                            'trigger':self.replenish_trigger,
                            'product_min_qty':self.replenish_product_min_qty,
                            'product_max_qty':self.replenish_product_min_qty,
                            'qty_multiple':self.replenish_qty_multiple
                        })

    def kits_action_create_update_putaway_rules(self):
        category = self.env['product.category'].search([('id', 'child_of', self.id)]) if self.include_subcategory else self
        for rec in category:
            if not self.putaway_location_in_id:
                raise UserError('Enter - When Product arrives in - First !')
            if not self.putaway_location_out_id:
                raise UserError('Enter - Store to sublocation - First !')
            related_products = self.env['product.product'].search([('categ_id','=',rec.id)])
            for product in related_products:
                putaway_replanish = self.env['stock.putaway.rule'].search([('product_id','=',product.id),('location_in_id','=',self.putaway_location_in_id.id),('location_out_id','=',self.putaway_location_out_id.id)])
                if not putaway_replanish:
                    self.env['stock.putaway.rule'].create({
                        'product_id':product.id,
                        'location_in_id':self.putaway_location_in_id.id,
                        'location_out_id':self.putaway_location_out_id.id,
                    })

    def action_create_bom(self):
        category = self.env['product.category'].search([('id', 'child_of', self.id)]) if self.include_subcategory else self
        for rec in category:
            related_product_tmpl = self.env['product.template'].search([('categ_id','=',rec.id),('detailed_type','=','product')])
            for product_tmpl in related_product_tmpl:
                mrp_bom = self.env['mrp.bom'].search([('product_tmpl_id','=',product_tmpl.id)])
                if not mrp_bom:
                    bom_line = []
                    for line in self.bom_category_line_ids:
                        bom_line.append((0,0,{'product_id':line.product_id.id,
                                              'product_qty':line.product_qty,
                                                'product_uom_id':line.product_uom_id.id}))
                    bom_id = self.env['mrp.bom'].create({
                        'product_tmpl_id':product_tmpl.id,
                        'product_qty':self.product_qty,
                        'type':self.bom_type,
                        'product_uom_id':product_tmpl.uom_id.id,
                        'bom_line_ids':bom_line
                    })
                    
                    
