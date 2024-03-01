from odoo import fields, models
from odoo.exceptions import UserError


class sale_order(models.Model):
    _inherit = 'sale.order'

    production_count = fields.Integer('Production Count',compute = 'compute_manufature_order_count' )
    production_ids = fields.One2many('mrp.production','sale_order_id',string='manufacturing orders')

    def compute_manufature_order_count(self):
        for order in self:
            order.production_count = len(order.production_ids)
    
    def kits_get_product_bom(self,product_id):
        bom_id = False
        if product_id.bom_ids:
            bom_id = product_id.bom_ids[0]
        elif product_id.product_tmpl_id.bom_ids:
            bom_id = product_id.product_tmpl_id.bom_ids[0]
        else:
            raise UserError('System can not generate Manufecturing order because BOM is missing for product %s'% (product_id.display_name))
        return bom_id

    def kits_create_mo(self,product_id,product_uom_qty,bom_id,uom_id):
        manufacture_obj = self.env['mrp.production']
        manufacture_id = manufacture_obj.create({
                'product_id' : product_id,
                'product_qty' : product_uom_qty,
                'bom_id' : bom_id,
                'product_uom_id' : uom_id,
                'sale_order_id' : self.id,
            })
        return manufacture_id
    
    def action_confirm(self):
        res = super(sale_order, self).action_confirm()
        #check if custom setting is enable, Custom flow will execute.
        create_production = self.env['ir.config_parameter'].sudo().get_param('kits_manufacture_on_demand.create_production')
        create_seprate_production = self.env['ir.config_parameter'].sudo().get_param('kits_manufacture_on_demand.create_separate_production')
        if create_production:
            stock_move_obj = self.env['stock.move'].sudo()
            for record in self:
                #If any product has no bom. then, user error will be raised by below function.
                record.check_avaiblity_of_bom_in_products()
                #if seprate production setting is enable.Then, manufacture order will be created as per order line.
                if create_seprate_production:
                    order_line = self.env['sale.order.line'].search([('order_id','=',record.id),('product_id.kits_manufacture_ok','=',True)])
                    for line in order_line:
                        bom_id = record.kits_get_product_bom(line.product_id)
                        manufacture_id = record.kits_create_mo(line.product_id.id,line.product_uom_qty,bom_id.id,line.product_id.uom_id.id)
                        stock_move_obj.create(manufacture_id._get_moves_raw_values())
                        stock_move_obj.create(manufacture_id._get_moves_finished_values())
                        manufacture_id._create_workorder()
                        manufacture_id.action_confirm()
                else:
                    product_ids = list(set(self.env['sale.order.line'].search([('order_id','=',record.id),('product_id.kits_manufacture_ok','=',True)]).mapped('product_id')))
                    for product_id in product_ids:
                        order_lines = record.order_line.filtered(lambda a:a.product_id == product_id)
                        qty = sum(order_lines.mapped('product_uom_qty'))
                        bom_id = record.kits_get_product_bom(product_id)
                        manufacture_id = record.kits_create_mo(product_id.id,qty,bom_id.id,product_id.uom_id.id)
                        stock_move_obj.create(manufacture_id._get_moves_raw_values())
                        stock_move_obj.create(manufacture_id._get_moves_finished_values())
                        manufacture_id._create_workorder()
                        manufacture_id.action_confirm()
        return res

    def check_avaiblity_of_bom_in_products(self):
        product_ids_display_name = []
        products_without_bom = '\n'
        product_ids = list(set(self.env['sale.order.line'].search([('order_id','=',self.id),('product_id.kits_manufacture_ok','=',True)]).mapped('product_id')))
        for product_id in product_ids:
            if not product_id.bom_ids and not product_id.product_tmpl_id.bom_ids:
                product_ids_display_name.append(product_id.display_name)
        products_without_bom +=  '\n'.join(product_ids_display_name)
        if product_ids_display_name:
            raise UserError('Please create bill of material for following products: %s'% (products_without_bom))
        
    def action_cancel(self):
        res = super(sale_order,self).action_cancel()
        if self.production_ids:
            self.production_ids.kits_cancel_manufacture()
        return res
        
    def action_display_manufacture_orders(self):
        return {
            'name': ('Manufacture Orders'),
            'domain': [('id', 'in', self.production_ids.ids)],
            'view_mode': 'tree,form',
            'res_model': 'mrp.production',
            'views': [[False, "tree"], [False, "form"]],
            'type': 'ir.actions.act_window'
        }