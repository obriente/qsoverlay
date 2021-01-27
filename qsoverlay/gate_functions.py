"""
gate_functions: functions that take a builder and insert a a given set
of gates, to be called from within the builder to execute either
composite gates, or gates not natively within quantumsim.
"""
import quantumsim.circuit
from numpy import pi


def X_gate(builder, bit, time):
    builder < ('RX', bit, -pi, time)


def Y_gate(builder, bit, time):
    builder < ('RY', bit, -pi, time)


def Z_gate(builder, bit, time):
    builder < ('RZ', bit, -pi, time)


def had_from_rot(builder, bit, time):
    """Creates a Hadamard gate from two rotations."""
    builder < ('RX', bit, -pi, time)
    builder < ('RY', bit, -pi / 2, time)


def CNOT_from_CZ(builder, bit0, bit1, time):
    """Creates a CNOT gate from a CZ gate"""
    builder < ('RY', bit1, -pi / 2, time)
    builder < ('CZ', bit0, bit1, time)
    builder < ('RY', bit1, pi / 2, time)


def CRX_from_CZ(builder, bit0, bit1, angle, time):
    """Creates a CNOT gate from a CZ gate"""
    builder < ('RY', bit1, -pi / 2, time)
    builder < ('RZ', bit0, -angle / 2, time)
    builder < ('CPhase', bit0, bit1, angle, time)
    builder < ('RY', bit1, pi / 2, time)


def insert_CZ(builder,
              bit0,
              bit1,
              time,
              dephase_var,
              quasistatic_flux=None,
              high_frequency=None):
    """
    Function to insert a CZ gate with an optional quasistatic flux noise.
    Currently the noise addition is fairly badly implemented, should be
    improved
    """
    circuit = builder.circuit

    g = quantumsim.circuit.NoisyCPhase(bit0=bit0,
                                       bit1=bit1,
                                       time=time,
                                       dephase_var=dephase_var)
    circuit.add_gate(g)

    if quasistatic_flux is not None:
        if high_frequency is False:
            raise ValueError('Sorry, current setup requires bit0 to be a ' +
                             'high-frequency qubit.')
        g2 = quantumsim.circuit.RotateZ(bit0, angle=quasistatic_flux,
                                        time=time * (1 + 1e-6))
        g2.quasistatic_flux_flag = True
        circuit.add_gate(g2)


def insert_CPhase(builder,
                  bit0,
                  bit1,
                  time,
                  angle,
                  dephase_var,
                  high_frequency=None,
                  quasistatic_flux=None):
    """
    Function to insert a CPhase gate with an optional quasistatic flux noise.
    Currently the noise addition is fairly badly implemented, should be
    improved
    """

    circuit = builder.circuit

    g = quantumsim.circuit.CPhaseRotation(angle=angle, bit0=bit0,
                                          bit1=bit1, time=time,
                                          dephase_var=dephase_var)

    circuit.add_gate(g)

    if quasistatic_flux is not None:
        if high_frequency is False:
            raise ValueError('Sorry, current setup requires bit0 to be a ' +
                             'high-frequency qubit.')
        g2 = quantumsim.circuit.RotateZ(bit0, angle=quasistatic_flux,
                                        time=time * (1 + 1e-6))
        g2.quasistatic_flux_flag = True
        circuit.add_gate(g2)


def insert_measurement(builder,
                       bit,
                       time,
                       interval_time,
                       msmt_time,
                       sampler,
                       output_bit,
                       p_exc_init=0,
                       p_dec_init=0,
                       p_exc_fin=0,
                       p_dec_fin=0,
                       real_output_bit=None):
    """
    Inserts gates for a measurement as per the butterfly setup.
    """
    circuit = builder.circuit

    # Add bit if not present in list
    if output_bit not in circuit.get_qubit_names():
        b = quantumsim.circuit.ClassicalBit(output_bit)
        circuit.add_qubit(b)
    if real_output_bit and real_output_bit not in circuit.get_qubit_names():
        b = quantumsim.circuit.ClassicalBit(real_output_bit)
        circuit.add_qubit(b)

    # Add decay pre-measurement
    if p_exc_init + p_dec_init > 0:
        g = quantumsim.circuit.ButterflyGate(
            bit, time=time, p_exc=p_exc_init, p_dec=p_dec_init)
        circuit.add_gate(g)

    # Add decay post-measurement
    if p_exc_fin + p_dec_fin > 0:
        g = quantumsim.circuit.ButterflyGate(
            bit, time=time + 2 * interval_time,
            p_exc=p_exc_fin, p_dec=p_dec_fin)
        circuit.add_gate(g)

    # Add measurement
    circuit.add_measurement(bit, time=time + interval_time,
                            sampler=sampler, output_bit=output_bit,
                            real_output_bit=real_output_bit)


def insert_reset(builder,
                 bit,
                 time,
                 reset_time,
                 population):
    circuit = builder.circuit
    reset_gate = quantumsim.circuit.ResetGate(
        bit=bit, time=time + reset_time, population=population)
    circuit.add_gate(reset_gate)
