from odoo import http
from odoo.http import request


class MKDashboard(http.Controller):

    @http.route('/base_marketplace/get_dashboard_data', type="json", auth='user')
    def fetch_dashboard_data(self, mk_instance_id=False, date_from=False, date_to=False, date_filter=False):
        if not mk_instance_id:
            mk_instance_id = request.env['mk.instance'].sudo().search([('state', '=', 'confirmed')])
            is_general_dashboard = True
        else:
            is_general_dashboard = False
            mk_instance_id = request.env['mk.instance'].sudo().search([('state', '=', 'confirmed'), ('id', '=', mk_instance_id)])
        dates_ranges = request.env['mk.instance']._get_mk_dashboard_dates_ranges()
        dashboard_data = mk_instance_id.get_mk_dashboard_data(date_from, date_to, dates_ranges.get(date_filter), date_filter, is_general_dashboard=is_general_dashboard)
        return {'dashboards': dashboard_data,
                'dates_ranges': dates_ranges}
