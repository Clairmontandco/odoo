from odoo import models,fields,api

class mrp_production(models.Model):
    _inherit = 'mrp.production'

    sales_description = fields.Text('Sale Description')

    def set_sale_description(self):
        for record in self:
            splited_origin = record.origin.split('-')
            if len(splited_origin) > 1:
                splited_origin = [i.strip() for i in splited_origin[1].split(',')]
                sale_id = self.env['sale.order'].search([('name','=',splited_origin[0])])
                sales_description = ''
                if sale_id:
                    lines = sale_id.order_line.filtered(lambda line: line.product_id == record.product_id)
                    for line in lines:
                        desc = line.name.replace(record.product_id.display_name,'')
                        if desc:
                            desc = desc.strip()
                            sales_description += desc+'\n\n'
                        else:
                            continue
            record.sales_description = sales_description.strip()


    @api.model
    def create(self,vals):
        res = super(mrp_production,self).create(vals)
        res.set_sale_description()
        return res
