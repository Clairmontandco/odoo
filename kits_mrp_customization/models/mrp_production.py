from odoo import models, fields, api,_
from datetime import datetime,date
class mrp_production(models.Model):
    _inherit = 'mrp.production'

    sales_description = fields.Text('Sale Description',compute="compute_sales_description",compute_sudo=True)
    # so_ids = fields.Many2many('sale.order','manufacturing_sale_order_rel','manufacturing_id','sale_id','Sale orders',compute="_compute_so_ids",store=True,compute_sudo=True,copy=False)
    so_ids = fields.Many2many('sale.order','manufacturing_sale_order_rel','manufacturing_id','sale_id','Sale orders',compute="compute_sales_description",store=True,compute_sudo=True,copy=False)
    expected_delivery_date = fields.Datetime('Delivery Date',compute="_compute_so_ids",compute_sudo=True,copy=False,store=True)

    @api.depends('sales_description','so_ids')
    def _compute_so_ids(self):
        for record in self:
            commitment_dates = [date for date in record.so_ids.mapped('commitment_date') if date and isinstance(date,datetime)]
            data = {
                'expected_delivery_date':min(commitment_dates) if len(commitment_dates) else False,
                }
            if len(record.so_ids.mapped("name")):
                data.update({'origin':','.join(record.so_ids.mapped('name'))})
            record.write(data)
    
    @api.depends('so_ids','state','product_id')
    def compute_sales_description(self):
        sales_description = ''
        so_ids = self.env['sale.order'].sudo()
        for record in self:
            if not record.sale_order_line_ids:
                #find default odoo sales orders
                for line in self.env['report.stock.report_product_product_replenishment']._get_report_lines(False,[record.product_id.id],[record.location_src_id.id]):
                    if line['document_in'] and line['document_in'] == record:
                        if isinstance(line['document_out'],so_ids.__class__):
                                so_ids |= line['document_out']
            else:
                #Find manufaturing on demand sales orders
                so_ids = record.sale_order_id

            for sol in so_ids.mapped('order_line').filtered(lambda x: x.product_id == record.product_id):
                if sol.name:
                    sales_description += sol.name+'\n\n'

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

