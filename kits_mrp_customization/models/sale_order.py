from odoo import models,fields,api,_

class sale_order(models.Model):
    _inherit = 'sale.order'

    mo_ids = fields.Many2many('mrp.production','manufacturing_sale_order_rel','sale_id','manufacturing_id','Manufacturings',copy=False)
    kits_mo_count = fields.Integer('#Manufacturings',compute="_compute_mo_count",copy=False)

    @api.depends('mo_ids')
    def _compute_mo_count(self):
        mo_obj = self.env['mrp.production']
        for record in self:
            mo_ids = mo_obj
            for line in record.order_line:
                lines = self.env['report.stock.report_product_product_replenishment']._get_report_lines(False,[line.product_id.id],[line.warehouse_id.lot_stock_id.id])
                for line in lines:
                    if line['document_out'] and line['document_out'] == record:
                        if isinstance(line['document_in'],mo_obj.__class__):
                            mo_ids |= line['document_in']
            # record.kits_mo_count = len(mo_ids)
            # record.mo_ids = mo_ids
            record.write({
                'kits_mo_count':len(mo_ids),
                'mo_ids':mo_ids.ids,
            })

    def action_view_manufacturings(self):
        self.ensure_one()
        action =  {
            'name':_('Manufacturing Orders'),
            'type':'ir.actions.act_window',
            'res_model':"mrp.production",
            'target':'current',
        }
        if len(self.mo_ids) == 1:
            action.update({
                'res_id':self.mo_ids.ids[0],
                'view_mode':'form',
            })
        else:
            action.update({
                'view_mode':'tree,form',
                'domain':[('id','in',self.mo_ids.ids)],
                })
        return action
