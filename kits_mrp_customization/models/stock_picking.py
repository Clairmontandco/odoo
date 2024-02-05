from odoo import _, api, fields, models, tools
from io import BytesIO
import base64
from openpyxl import load_workbook,Workbook
from openpyxl.styles import Border, Side, Alignment, Font

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    invoice_payment_status = fields.Selection(related = 'sale_id.invoice_payment_status')
    sale_user_id = fields.Many2one('res.users',related = 'sale_id.user_id')
    sale_team_id = fields.Many2one('crm.team',related = 'sale_id.team_id')

    def action_kits_batch_order_excel(self):
        wb = Workbook()
        wrksheet = wb.active
        wrksheet.title = "Batch Order Excel"        
        header_font = Font(name='Lato', size=12, bold=True)
        value_font = Font(name='Lato', size=12, bold=False)
        
        wrksheet.cell(row=1,column=1).value = "Scheduled Date"
        wrksheet.cell(row=1,column=1).font = header_font
        wrksheet.column_dimensions['A'].width = 20
        wrksheet.cell(row=1,column=2).value = "Deadline"
        wrksheet.cell(row=1,column=2).font = header_font
        wrksheet.column_dimensions['B'].width = 20
        
        wrksheet.cell(row=1,column=3).value = "Contact"
        wrksheet.cell(row=1,column=3).font = header_font
        wrksheet.column_dimensions['C'].width = 30
        wrksheet.cell(row=1,column=4).value = "Source Document"
        wrksheet.cell(row=1,column=4).font = header_font
        wrksheet.column_dimensions['D'].width = 20
        
        wrksheet.cell(row=1,column=5).value = "Product"
        wrksheet.cell(row=1,column=5).font = header_font
        wrksheet.column_dimensions['E'].width = 30
        wrksheet.cell(row=1,column=6).value = "Internal Reference"
        wrksheet.cell(row=1,column=6).font = header_font
        wrksheet.column_dimensions['F'].width = 20
        wrksheet.cell(row=1,column=7).value = "Product Category"
        wrksheet.cell(row=1,column=7).font = header_font
        wrksheet.column_dimensions['G'].width = 30
        wrksheet.cell(row=1,column=8).value = "Demand"
        wrksheet.cell(row=1,column=8).font = header_font
        wrksheet.column_dimensions['H'].width = 10
        row_index = 2
        for rec in self.filtered(lambda x:x.state != 'cancel'):
            
            wrksheet.cell(row=row_index, column=1).value = rec.scheduled_date
            wrksheet.cell(row=row_index, column=2).value = rec.date_deadline
            wrksheet.cell(row=row_index, column=3).value = rec.partner_id.name
            wrksheet.cell(row=row_index, column=4).value = rec.origin
            wrksheet.cell(row=row_index, column=1).font = value_font
            wrksheet.cell(row=row_index, column=2).font = value_font
            wrksheet.cell(row=row_index, column=3).font = value_font
            wrksheet.cell(row=row_index, column=4).font = value_font
        
            move_ids = rec.move_ids_without_package.filtered(lambda x:x.state != 'cancel')
            for move in move_ids:
                # Value
                wrksheet.cell(row=row_index, column=5).value = move.name
                wrksheet.cell(row=row_index, column=6).value = move.product_id.default_code
                wrksheet.cell(row=row_index, column=7).value = move.product_id.categ_id.complete_name
                wrksheet.cell(row=row_index, column=8).value = move.product_uom_qty
               
                
                # Adding Font
                wrksheet.cell(row=row_index, column=5).font = value_font
                wrksheet.cell(row=row_index, column=6).font = value_font
                wrksheet.cell(row=row_index, column=7).font = value_font
                wrksheet.cell(row=row_index, column=8).font = value_font
               
                
                row_index += 1
                    
        fp = BytesIO()
        wb.save(fp)
        fp.seek(0)
        data = fp.read()
        fp.close()
        wizard_id = self.env['report.wizard'].create({'file':base64.b64encode(data)})

        return {
            'type': 'ir.actions.act_url',
            'url': 'web/content/?model=report.wizard&download=true&field=file&id=%s&filename=%s.xlsx' % (wizard_id.id,'Batch_Order_Excel'),
            'target': 'self',
        }

    def preview_sale_order(self):
        for rec in self:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'sale.order',
                'view_type': 'form',
                'view_mode': 'form',
                'res_id': rec.sale_id.id,
                'target': 'current'
            }
