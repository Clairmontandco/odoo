from odoo import models, fields, api, _
from odoo.tools.translate import _
from odoo.exceptions import Warning

class python_script_runner(models.Model):
    _name = "python.script.runner"
    _description = 'Python Script Runner'
    
    name=fields.Char(string='Name',size=1024,required=True)
    code=fields.Text(string='Python Code',required=True)
    result=fields.Text(string='Result',readonly=True)
        
    
    def execute_script(self):
        localdict = {'self':self,'user_obj':self.env.user}
        for obj in self:
            try :
                exec(obj.code, localdict)
                if localdict.get('result', False):
                    self.write({'result':localdict['result']})
                else : 
                    self.write({'result':''})
            except Exception as e:
                raise Warning('Python code is not able to run ! message : %s' %(e))
                
        return True
    
    
    