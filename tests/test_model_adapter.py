"""Contratos del adaptador con generador simulado; no mide un modelo real."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
import pipeline
import load_qwen
import model_extract as ia


class TokenizerFixture:
    def apply_chat_template(self, *args, **kwargs):
        return [1, 2, 3]


class AdapterTests(unittest.TestCase):
    def empty(self, **reps):
        d = {c: [] if c in ('socios', 'representantes_legales', 'poderes') else None for c in pipeline.CAMPOS}
        d.update(reps)
        return d

    def fake_generation(self, paquete, *args, **kwargs):
        return {'estado': 'generada', 'respuesta_cruda': '{"valores":[]}', 'tokens_salida': 5,
                'segundos': 0, 'limite_tokens_alcanzado': False, 'limite_tiempo_alcanzado': False}

    def test_abstencion_neural_no_se_rellena_con_reglas(self):
        lectura = json.loads((ROOT / 'resultados/sinteticos/archivados/01_acta_constitucion_A/LECTURA/LECTURA.json').read_text())
        reglas = self.empty(razon_social='VALOR DE REGLAS QUE NO ES RESPUESTA NEURAL')
        with tempfile.TemporaryDirectory() as tmp, patch.object(load_qwen, 'cargar', return_value=(object(), TokenizerFixture(), {'modelo': 'fixture_sin_red'})), patch.object(ia, 'preparar', side_effect=lambda campo,*a,**k:{'campo':campo,'citas':[],'mensajes':[]}), patch.object(ia, 'generar', side_effect=self.fake_generation) as generador:
            datos, _, control = pipeline.qwen(lectura, reglas, Path(tmp), lambda _:None)
            self.assertEqual(generador.call_count, 8)
            self.assertIsNone(datos['razon_social'])
            self.assertEqual(control['motor'], 'qwen')
            pipeline.validar(datos, control)

    def test_designacion_personal_y_referencias_reconciliadas_se_integran_sin_gpu(self):
        textos = [
            'VIGÉSIMA OCTAVA.- El Administrador Único o el Consejo de Administración gozará de las facultades siguientes. A) PODER GENERAL PARA ACTOS DE ADMINISTRACIÓN. VIGÉSIMA NOVENA.- Otra cláusula.',
            'TERCERO.- La administración de la sociedad estará a cargo de un Consejo de Administración, designando en este momento al señor ANA TORRES PRUEBA como PRESIDENTE y al señor LUIS RAMOS DEMO como SECRETARIO. Les confieren al Consejo de Administración en lo individual a cada uno de sus miembros para que ejerciten conjunta o separadamente las facultades que se mencionan en la cláusula Vigésima Octava. CUARTO.- Cierre.'
        ]
        lectura = {'archivo':'fixture.pdf','sha256_pdf':'f'*64,'paginas':[{'pagina':i,'fuente_id':f'fixture:p{i}', 'texto':t} for i,t in enumerate(textos,1)]}
        original_schema = ia.esquema_salida

        def generar(paquete, *args, **kwargs):
            g = self.fake_generation(paquete)
            if paquete['campo'] == 'representantes_legales':
                g['respuesta_cruda'] = json.dumps({'valores':[
                    {'ref':'S2','texto':'ANA TORRES PRUEBA','rol':'presidente','ref_otorgamiento':'S2','refs_facultades':['S1']},
                    {'ref':'S2','texto':'LUIS RAMOS DEMO','rol':'secretario','ref_otorgamiento':'S2','refs_facultades':['S1']}]})
            return g

        with tempfile.TemporaryDirectory() as tmp, patch.object(load_qwen,'cargar',return_value=(object(),TokenizerFixture(),{'modelo':'fixture_sin_red'})), patch.object(ia,'preparar',side_effect=lambda campo,*a,**k:{'campo':campo,'citas':[],'mensajes':[]}), patch.object(ia,'generar',side_effect=generar):
            datos, ev, control = pipeline.qwen(lectura, self.empty(), Path(tmp), lambda _:None)
            self.assertEqual(datos['representantes_legales'], ['ANA TORRES PRUEBA', 'LUIS RAMOS DEMO'])
            self.assertTrue(ev['representantes_legales'])
            self.assertIs(ia.esquema_salida, original_schema)
            self.assertFalse(control['aprobado'])
            self.assertTrue((Path(tmp)/'QWEN/RECONCILIACION_REFERENCIAS.json').exists())
            pipeline.validar(datos, control)


if __name__ == '__main__':
    unittest.main()
