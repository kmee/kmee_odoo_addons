# -*- coding: utf-8 -*-
# Bianca da Rocha Bartolomei <bianca.bartolomei@kmee.com.br>
# Copyright 2018 KMEE INFORMATICA LTDA
# License AGPL-3 or later (http://www.gnu.org/licenses/agpl)

from openerp import models, fields, _
import base64
import zipfile
import datetime
from pysped.nfe.leiaute.consrecinfe_310 import ProcNFe
from openerp.exceptions import Warning as UserError

class ImportarNFe(models.TransientModel):
    _name = 'importar.nfe.wizard'
    _description = 'Importar NFe'


    caminho = fields.Char(
        string='Caminho',
        help='Caminho do diretório do arquivo de upload. '
             'Ex: "/home/usuario/documentos/"',
    )

    arquivo_nfe = fields.Many2many(
        'ir.attachment',
        string='Arquivos',
        help='Arquivos com extensão .xml, .zip ou .whl',
    )


    def importar_nfe(self, cr, uid, ids, context=None):

        arquivos = self.browse(cr, uid, ids, context)[0]
        data = []

        for arq in arquivos.arquivo_nfe:
            # tratamento caso o arquivo seja um zip
            if (arq.name.lower().endswith(('.zip', '.whl')) or
                    zipfile.is_zipfile(arq.name)):

                filename = arquivos.caminho + arq.name

                try:
                    zipfp = open(filename, 'rb')
                    zip = zipfile.ZipFile(zipfp, allowZip64=True)

                except:
                    raise UserError(
                            "Arquivo não encontrado. Verifique se o "
                            "caminho está escrito corretamente.")

                # busca os arquivos comprimidos e coloca as
                # informações deles numa lista
                for info in zip.infolist():
                    name = info.filename
                    data.append(zip.read(name))

            # caso o arquivo seja um xml, coloca sua informação na mesma lista
            elif arq.name.lower().endswith(('.xml')):
                data.append(base64.decodestring(arq.datas))

        for inv in data:
            event_obj = arquivos.env['l10n_br_account.document_event']

            results = []
            protNFe = {}
            protNFe["state"] = 'sefaz_exception'
            protNFe["status_code"] = ''
            protNFe["message"] = ''
            protNFe["nfe_protocol_number"] = ''

            try:
                nfe_obj = ProcNFe()
                nfe_obj.set_xml(inv.decode("utf-8"))

                # busca o documento ao qual o xml se refere
                documento_origem = arquivos.env[
                    'account.invoice'].search([('internal_number', '=',
                                                nfe_obj.NFe.infNFe.ide.
                                                nNF.valor)])

                # monta o evento do documento de origem
                vals = {
                    'type': '1',
                    'status': nfe_obj.protNFe.infProt.cStat.valor,
                    'response': '',
                    'company_id': documento_origem.company_id.id,
                    'origin': '[NF-E]' + documento_origem.internal_number,
                    'message': nfe_obj.protNFe.infProt.xMotivo.valor,
                    'state': 'done',
                    'document_event_ids': documento_origem.id
                }

                results.append(vals)

                # coloca as informações adicionais do xml
                protNFe["nfe_access_key"] = nfe_obj.protNFe.infProt.chNFe.valor
                protNFe["status_code"] = nfe_obj.protNFe.infProt.cStat.valor
                protNFe["nfe_protocol_number"] = \
                    nfe_obj.protNFe.infProt.nProt.valor
                protNFe["message"] = nfe_obj.protNFe.infProt.xMotivo.valor

                # muda o estado do documento de origem
                if nfe_obj.protNFe.infProt.cStat.valor in ('100', '150'):
                    protNFe["state"] = 'open'
                    documento_origem.invoice_validate()
                elif nfe_obj.protNFe.infProt.cStat.valor in ('110', '301','302'):
                    protNFe["state"] = 'sefaz_denied'

            except Exception as e:
                _logger.error(e.message, exc_info=True)
                vals = {
                    'type': '-1',
                    'status': '000',
                    'response': 'response',
                    'company_id': documento_origem.company_id.id,
                    'origin': '[NF-E]' + documento_origem.internal_number,
                    'file_sent': 'False',
                    'file_returned': 'False',
                    'message': 'Erro desconhecido ' + str(e),
                    'state': 'done',
                    'document_event_ids': documento_origem.id
                }
                results.append(vals)

            finally:
                # escreve os as informações modificadas acima
                for result in results:
                    if result['type'] == '0':
                        event_obj.write(result)
                    else:
                        event_obj.create(result)

                documento_origem.write({
                    'nfe_status': protNFe["status_code"] + ' - ' +
                    protNFe["message"],
                    'nfe_date': datetime.datetime.now(),
                    'state': protNFe["state"],
                    'nfe_protocol_number': protNFe["nfe_protocol_number"],
                    'nfe_access_key': protNFe["nfe_access_key"]
                })
        return True
