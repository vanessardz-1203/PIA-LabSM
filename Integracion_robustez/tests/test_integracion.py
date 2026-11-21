"""Pruebas de integración del motor, coordinación y registro de métricas."""
from Integracion_robustez.simulacion.motor import MotorSimulacion
from Integracion_robustez.simulacion.robustez import Evento


def test_motor_crea_modulos_reales():
    motor = MotorSimulacion(drones=2, pasos=3, usar_relevos=False)
    assert len(motor.drones) == 2
    assert motor.coordinador is not None
    assert motor.entorno.sectores


def test_motor_registra_cobertura_y_falla():
    motor = MotorSimulacion(
        drones=2, pasos=3, usar_relevos=False,
        eventos=[Evento(paso=2, tipo='falla_dron', dron_id=1)],
    )
    resultado = motor.ejecutar()
    assert resultado['pasos'] == 3
    assert resultado['eventos_aplicados'] == 1
    assert len(motor.registros_dict()) == 3
    assert 0 <= resultado['cobertura_inst_media_pct'] <= 100
