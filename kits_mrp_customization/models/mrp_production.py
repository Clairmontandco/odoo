from odoo import models, fields, api,_
from datetime import datetime

class mrp_production(models.Model):
    _inherit = 'mrp.production'

    sales_description = fields.Text('Sale Description',compute="compute_sales_description",compute_sudo=True)
    # so_ids = fields.Many2many('sale.order','manufacturing_sale_order_rel','manufacturing_id','sale_id','Sale orders',compute="_compute_so_ids",store=True,compute_sudo=True,copy=False)
    so_ids = fields.Many2many('sale.order','manufacturing_sale_order_rel','manufacturing_id','sale_id','Sale orders',compute="compute_sales_description",store=True,compute_sudo=True,copy=False)
    expected_delivery_date = fields.Datetime('Delivery Date',compute="_compute_so_ids",compute_sudo=True,copy=False,store=True)

    @api.depends('sales_description','so_ids')
    def _compute_so_ids(self):
        sale_obj = self.env['sale.order']
        for record in self:
            # so_ids = sale_obj
            # lines = self.env['report.stock.report_product_product_replenishment']._get_report_lines(False,[record.product_id.id],[record.location_src_id.id])
            # for line in lines:
            #     if line['document_in'] == self:
            #         if line['document_out']:
            #             if isinstance(line['document_out'],sale_obj.__class__):
            #                 so_ids |= line['document_out']
            
            # commitment_dates = [date for date in so_ids.mapped('commitment_date') if date and isinstance(date,datetime)]
            commitment_dates = [date for date in record.so_ids.mapped('commitment_date') if date and isinstance(date,datetime)]
            data = {
                # 'so_ids':[(6,0,so_ids.ids)],
                'expected_delivery_date':min(commitment_dates) if len(commitment_dates) else False,
                }
            # if len(so_ids.mapped("name")):
            #     data.update({'origin':','.join(so_ids.mapped('name'))})
            if len(record.so_ids.mapped("name")):
                data.update({'origin':','.join(record.so_ids.mapped('name'))})
            record.write(data)
    
    @api.depends('so_ids')
    def compute_sales_description(self):
        sale_obj = self.env['sale.order']
        for record in self:
            so_ids = self.env['sale.order'].search([('mo_ids','in',record.ids)])
            sales_description = ''
            for sol in so_ids.mapped('order_line').filtered(lambda x: x.product_id == record.product_id):
                desc = sol.name.replace(record.product_id.display_name,'').strip()
                if desc:
                    sales_description += desc+'\n\n'
                else:
                    continue
            # record.sales_description = sales_description.strip()
            # record.so_ids = [(6,0,so_ids.ids)]
            record.write({'sales_description':sales_description.strip(),'so_ids':so_ids.ids})
        
    @api.depends('so_ids','sales_description')
    def _compute_sale_order_count(self):
        # Replaced to count sale orders from field - so_ids
        for record in self:
            record.sale_order_count = len(record.so_ids)
    
    def aciton_show_sale_orders(self):
        # Replace method to show Sale orders from field - so_ids
        action = {
            'name': _("Sources Sale Orders of %s", self.name),
            'res_model': 'sale.order',
            'type': 'ir.actions.act_window',
        }
        if len(self.so_ids.ids) == 1:
            action.update({
                'view_mode': 'form',
                'res_id': self.so_ids.ids[0],
            })
        else:
            action.update({
                'domain': [('id', 'in', self.so_ids.ids)],
                'view_mode': 'tree,form',
            })
        return action

    @api.model
    def create(self, vals):
        res = super(mrp_production, self).create(vals)
        # res._compute_so_ids()
        # res._compute_sale_order_count()
        return res
