import pprint
from .. import shopify
import urllib.parse as urlparse
from odoo import fields, models, tools
from odoo.exceptions import AccessError


class Partner(models.Model):
    _inherit = "res.partner"

    def fetch_all_shopify_customers(self, instance_id):
        try:
            shopify_customer_list, api_limit = [], 250
            page_info = False
            while 1:
                if instance_id.last_customer_import_date:
                    if page_info:
                        page_wise_customer_list = shopify.Customer().find(limit=api_limit, page_info=page_info)
                    else:
                        page_wise_customer_list = shopify.Customer().find(updated_at_min=instance_id.last_customer_import_date, limit=api_limit)
                else:
                    if page_info:
                        page_wise_customer_list = shopify.Customer().find(limit=api_limit, page_info=page_info)
                    else:
                        page_wise_customer_list = shopify.Customer().find(limit=api_limit)
                page_url = page_wise_customer_list.next_page_url
                parsed = urlparse.parse_qs(page_url)
                page_info = parsed.get('page_info', False) and parsed.get('page_info', False)[0] or False
                shopify_customer_list += page_wise_customer_list
                if not page_info:
                    break
            instance_id.last_customer_import_date = fields.Datetime.now()
            return shopify_customer_list
        except Exception as e:
            raise AccessError(e)

    def shopify_get_find_partner_where_clause(self, type):
        if type in ['invoice', 'delivery']:
            where_caluse = ['name', 'state_id', 'city', 'zip', 'street', 'street2', 'country_id', 'email', 'parent_id']
        else:
            where_caluse = ['name', 'state_id', 'city', 'zip', 'street', 'street2', 'country_id', 'email']
        return where_caluse

    def _extract_customer_data_from_shopify_dict(self, customer_dict, mk_instance_id, type='contact'):
        default_address_dict = customer_dict.get('default_address') if customer_dict and customer_dict.get('default_address', False) else customer_dict
        if not default_address_dict:
            return False
        name = default_address_dict.get('name', False)
        company_type = 'person'
        if mk_instance_id.is_create_company_contact and type == 'contact':
            name = default_address_dict.get('company', customer_dict.get('company')) or default_address_dict.get('name', False)
            company_type = 'company' if default_address_dict.get('company', False) or customer_dict.get('company', False) else 'person'
        if not name:
            if customer_dict.get('first_name', '') or customer_dict.get('last_name', ''):
                name = "{} {}".format(customer_dict.get('first_name', ''), customer_dict.get('last_name', ''))
            else:
                name = default_address_dict.get('email') or customer_dict.get('email') or "Untitled"
        country = self.env['res.country'].search(['|', ('code', '=', default_address_dict.get('country_code')), ('name', '=', default_address_dict.get('country_name'))], limit=1)
        state = self.env['res.country.state'].search(
            [('country_id', '=', country.id), '|', ('code', '=', default_address_dict.get('province_code')), ('name', '=', default_address_dict.get('province'))], limit=1)
        if not state and default_address_dict.get('province') and default_address_dict.get('province_code'):
            state = self.env['res.country.state'].with_context(tracking_disable=True).create(
                {'country_id': country.id, 'name': default_address_dict.get('province'), 'code': default_address_dict.get('province_code')})
        tag_list = []
        if customer_dict.get('tags', False):
            tag_list = self.shopify_prepare_tag_vals(customer_dict.get('tags'))
        partner_vals = {
            'name': name,
            'email': default_address_dict.get('email') or customer_dict.get('email'),
            'street': default_address_dict.get('address1'),
            'street2': default_address_dict.get('address2'),
            'city': default_address_dict.get('city'),
            'state_id': state.id,
            'country_id': country.id,
            'zip': default_address_dict.get('zip'),
            'phone': default_address_dict.get('phone') or customer_dict.get('phone'),
            'type': type,
            'comment': customer_dict.get('note', ''),
            'company_type': company_type,
            'category_id': tag_list,
        }
        return partner_vals

    def create_update_shopify_customers(self, customer_dict, mk_instance_id, type='contact', parent_id=False):
        mk_log_id = self.env.context.get('mk_log_id', False)
        queue_line_id = self.env.context.get('queue_line_id', False)
        partner = self.env['res.partner']
        try:
            partner_vals = self._extract_customer_data_from_shopify_dict(customer_dict, mk_instance_id, type=type)
            if partner_vals:
                partner = self.get_marketplace_partners(partner_vals, mk_instance_id, type=type, parent_id=parent_id)
                shopify_category_id = self.env.ref('shopify.res_partner_category_shopify', raise_if_not_found=False)
                if shopify_category_id:
                    partner.category_id = [(4, shopify_category_id.id)]
        except Exception as err:
            log_message = 'IMPORT CUSTOMER: IMPORT CUSTOMER: TECHNICAL EXCEPTION : {}'.format(err)
            self.env['mk.log'].create_update_log(mk_instance_id=mk_instance_id, mk_log_id=mk_log_id,
                                                 mk_log_line_dict={'error': [{'log_message': log_message, 'queue_job_line_id': queue_line_id and queue_line_id.id or False}]})
            queue_line_id and queue_line_id.write({'state': 'failed'})
        return partner

    def shopify_import_customers(self, instance_id):
        instance_id.connection_to_shopify()
        shopify_customer_list = self.fetch_all_shopify_customers(instance_id)
        if shopify_customer_list:
            batch_size = instance_id.queue_batch_limit or 100
            for shopify_customers in tools.split_every(batch_size, shopify_customer_list):
                queue_id = instance_id.action_create_queue(type='customer')
                for customer in shopify_customers:
                    customer_dict = customer.to_dict()
                    name = "%s %s" % (customer_dict.get('first_name') or '', customer_dict.get('last_name') or '')
                    line_vals = {
                        'mk_id': customer_dict.get('id') or '',
                        'state': 'draft',
                        'name': name.strip(),
                        'data_to_process': pprint.pformat(customer_dict),
                        'mk_instance_id': instance_id.id,
                    }
                    queue_id.action_create_queue_lines(line_vals)
        return True

    def shopify_prepare_tag_vals(self, shopify_tags):
        shopify_tag_list, shopify_tag_obj = [], self.env['res.partner.category']
        for tag in shopify_tags.split(','):
            if len(tag) < 1:
                continue
            shopify_tag_id = shopify_tag_obj.search([('name', '=', tag)], limit=1)
            if not shopify_tag_id:
                shopify_tag_id = shopify_tag_obj.create({'name': tag})
            shopify_tag_list.append(shopify_tag_id.id)
        return [(6, 0, shopify_tag_list)]
