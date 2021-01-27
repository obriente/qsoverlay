"""
circuit_builder: an overlay for quantumsim to build circuits slightly easier.
Assumes a gate set for a system, and inserts new gates end-on, keeping track
of at what time the next gate can be executed.

Does not do any compilation; this should possibly be inserted later.
"""

import numpy as np
import quantumsim.circuit
import quantumsim.ptm
from .update_functions import update_function_dic


class Builder:

    def __init__(self,
                 setup=None,
                 qubit_dic=None,
                 gate_dic=None,
                 gate_set=None,
                 update_rules=None,
                 **kwargs):
        '''
        qubit_dic: list of the qubits in the system.
            Each qubit should have a set of parameters,
            which is called whenever required by the gates.
        gate_dic: a dictionary of allowed gates.
            Each 'allowed gate' consists of:
                - the function to be called
                - a set of 'qubit_args' that will be found in
                    the qubit dictionary and passed to the gate.
                - a 'time' - the length of the gate
            Note that 'Measure' should be in the gate_set
        gate_set: a dictionary of allowed gate instances.
            An allowed gate instance is a list of the gate
            along with the qubits it is performed between.
        update_rules: a set of rules for updating the system.
            (i.e. between experiments).

        kwargs: Can add t1 and t2 via the kwargs instead of
            passing them with the qubit_dic.
        '''
        if setup is not None:
            self.qubit_dic = setup.qubit_dic
            self.gate_dic = setup.gate_dic
            self.gate_set = setup.gate_set
            self.update_rules = setup.update_rules
        else:
            self.qubit_dic = qubit_dic or {}
            self.gate_dic = gate_dic or {}
            self.gate_set = gate_set or {}
            self.update_rules = update_rules or []

        self.save_flag = True
        self.new_circuit(**kwargs)

    def new_circuit(self, circuit_title='New Circuit', **kwargs):

        '''
        Make a new circuit within the builder.
        '''

        self.circuit = quantumsim.circuit.Circuit(circuit_title)

        # Update the circuit list
        self.circuit_list = []

        # Times stores the current time of every qubit (beginning at 0)
        self.times = {}

        # Make qubits
        for qubit, qubit_args in sorted(self.qubit_dic.items()):

            if 'classical' in qubit_args.keys() and\
                    qubit_args['classical'] is True:
                self.circuit.add_qubit(quantumsim.circuit.ClassicalBit(qubit))
                continue

            # Get t1 values if we can, otherwise assume infinite.
            if 't1' not in qubit_args.keys():
                if 't1' in kwargs.keys():
                    qubit_args['t1'] = kwargs['t1']
                else:
                    qubit_args['t1'] = np.inf
            if 't2' not in qubit_args.keys():
                if 't2' in kwargs.keys():
                    qubit_args['t2'] = kwargs['t2']
                else:
                    qubit_args['t2'] = np.inf

            self.circuit.add_qubit(qubit, qubit_args['t1'], qubit_args['t2'])

            # Initialise the time of the latest gate on each qubit to 0
            self.times[qubit] = 0

    def make_reverse_circuit(self, title='reversed',
                             finalize=True):

        '''
        Generates a new builder with all gates put in the opposite
        order and reversed. (assumes every gate without an angle
        is self-inverse, which is true for CPhase, CNOT, Hadamard
        gates but not for ISwap gates - this is a bug that needs
        to be fixed.)
        '''

        reversed_circuit_list = list(reversed(self.circuit_list))
        for n, gate_desc in enumerate(reversed_circuit_list):
            gate_name = gate_desc[0]

            num_qubits = self.gate_dic[gate_name]['num_qubits']
            user_kws = self.gate_dic[gate_name]['user_kws']

            if 'angle' in user_kws:
                gate_desc = list(gate_desc)
                angle_index = user_kws.index('angle')
                gate_desc[num_qubits + 1 + angle_index] *= -1
                reversed_circuit_list[n] = tuple(gate_desc)

        reversed_circuit_builder = Builder(qubit_dic=self.qubit_dic,
                                           gate_dic=self.gate_dic,
                                           gate_set=self.gate_set,
                                           update_rules=self.update_rules)
        reversed_circuit_builder.add_circuit_list(reversed_circuit_list)
        if finalize:
            reversed_circuit_builder.finalize()

        return reversed_circuit_builder

    def add_qasm(self, qasm_generator, qubits_first=True, **params):
        '''
        Converts a qasm file into a circuit.
        qasm_generator should yield lines of qasm when called.

        I assume that qasm lines take the form:
        GATE [arg0, arg1, ..] qubit0 [qubit1, ..]
        Importantly, currently only allowing for a single space
        in between words.
        '''
        returned_gate_list = []
        for line in qasm_generator:

            # Copy kwargs to prevent overwriting
            kwargs = {**params}

            # Get positions of spaces in line
            spaces = [i for i, x in enumerate(line) if x == ',' or x == ' ']
            spaces.append(len(line))

            # Get the gate name
            gate_name = line[:spaces[0]]

            num_qubits = self.gate_dic[gate_name]['num_qubits']
            user_kws = self.gate_dic[gate_name]['user_kws']

            if gate_name == 'measure':
                # line looks like 'measure q -> c;'
                qubit_list = [line[spaces[0]+1:spaces[1]]]
                output_bit = [line[spaces[2]+1:spaces[3]]]
                self.add_gate('Measure', qubit_list,
                              output_bit=output_bit)
                continue

            if qubits_first:
                # Create qubit list
                qubit_list = [line[spaces[j]+1:
                              spaces[j+1]]
                              for j in range(num_qubits)]

                # Add arguments from qasm to kwargs
                for n, kw in enumerate(user_kws):
                    try:
                        kwargs[kw] = float(line[spaces[n+num_qubits]+1:
                                                spaces[n + num_qubits+1]])
                    except:
                        kwargs[kw] = line[spaces[n+num_qubits]+1:
                                          spaces[n+num_qubits+1]]

            else:
                # Add arguments from qasm to kwargs
                for n, kw in enumerate(user_kws):
                    try:
                        kwargs[kw] = float(line[spaces[n]+1:spaces[n+1]])
                    except Exception:
                        kwargs[kw] = line[spaces[n]+1:spaces[n+1]]

                # Create qubit list
                qubit_list = [line[spaces[len(user_kws)+j]+1:
                              spaces[len(user_kws)+j+1]]
                              for j in range(num_qubits)]

            try:
                returned_gate = self.add_gate(gate_name, qubit_list, **kwargs)
                if returned_gate is not None:
                    returned_gate_list.append(returned_gate)
            except Exception as inst:
                print()
                print('Adding gate failed!')
                try:
                    print(kwargs['angle'])
                except:
                    pass
                print(line, gate_name, qubit_list, kwargs)
                raise inst

        return returned_gate_list

    def add_circuit_list(self, circuit_list):

        '''
        Adds a circuit in the list format stored by qsoverlay
        to the builder.
        '''
        adjustable_gates = []
        for gate_desc in circuit_list:
            temp_ag = self < gate_desc
            if temp_ag:
                adjustable_gates.append(temp_ag)
        return adjustable_gates

    def __lt__(self, gate_desc):

        if type(gate_desc[0]) is not str:
            return self.add_gates_simultaneous(gate_desc)

        gate_name = gate_desc[0]

        num_qubits = self.gate_dic[gate_name]['num_qubits']
        user_kws = self.gate_dic[gate_name]['user_kws']
        time = None

        if len(gate_desc) == len(user_kws) + num_qubits + 2:
            if type(gate_desc[-1]) is bool:
                return_flag = gate_desc[-1]
            else:
                return_flag = False
                time = gate_desc[-1]
        elif len(gate_desc) == len(user_kws) + num_qubits + 3:
            assert gate_desc[-1] == bool
            assert gate_desc[-2] == float or gate_desc[-2] == int
            return_flag = gate_desc[-1]
            time = gate_desc[-2]
        else:
            assert len(gate_desc) == len(user_kws) + num_qubits + 1
            return_flag = False

        qubit_list = gate_desc[1:num_qubits + 1]

        kwargs = {kw: arg for kw, arg in
                  zip(user_kws, gate_desc[num_qubits+1:])}
        if time:
            kwargs['time'] = time

        return self.add_gate(gate_name, qubit_list,
                             return_flag=return_flag, **kwargs)

    def add_gates_simultaneous(self, gate_descriptions):
        '''
        takes a set of gate descriptions and begins the gates
        at the same time.
        '''
        starting_time = max([
            self.times[gate_desc[j]]
            for gate_desc in gate_descriptions
            for j in range(1, self.gate_dic[gate_desc[0]]['num_qubits']+1)])

        for gate_desc in gate_descriptions:
            num_qubits = self.gate_dic[gate_desc[0]]['num_qubits']
            qubit_list = gate_desc[1:num_qubits + 1]
            for qubit in qubit_list:
                self.times[qubit] = starting_time

        for gate_desc in gate_descriptions:
            gate_desc > self

    def add_gate(self, gate_name,
                 qubit_list, return_flag=False,
                 **kwargs):
        """
        Adds a gate at the appropriate time to our system.
        The gate is always added in the middle of the time period
        in which it occurs.

        @ gate_name: name of the gate in the gate_set dictionary
        @ qubit_list: list of qubits that the gate acts on (in
            whatever order is appropriate)
        @ kwargs: whatever is additionally necessary for the gate.
            e.g. classical bit output names for a measurement,
                angles for a rotation gate.
            Note: times, or error parameters that can be obtained
                from a qubit will be ignored.
        """

        # The gate tuple is a unique identifier for the gate, allowing
        # for asymmetry (as opposed to the name of the gate, which is
        # the same for every qubit/pair of qubits).
        gate_tuple = (gate_name, *qubit_list)

        circuit_args, builder_args = self.gate_set[gate_tuple]

        # kwargs is the list of arguments that gets passed to the gate
        # itself. We initiate with the set of additional arguments passed
        # by the user and the arguments from the gate dic intended for
        # quantumsim.
        kwargs = {**circuit_args, **kwargs}

        # Find the length of the gate
        gate_time = builder_args['gate_time']

        if 'time' in kwargs:
            time_flag = True
        else:
            time_flag = False
            # Calculate when to apply the gate
            time = max(self.times[qubit] for qubit in qubit_list)
            try:
                kwargs['time'] = time + builder_args['exec_time']

            except:
                # If we have no exec time, assume the gate occurs in the
                # middle of the time window allocated.
                kwargs['time'] = time + gate_time/2

        # Add qubits to the kwargs as appropriate.
        # Note that we do *not* add classical bits here.
        if len(qubit_list) == 1:
            kwargs['bit'] = qubit_list[0]
        else:
            for j, qubit in enumerate(qubit_list):
                kwargs['bit'+str(j)] = qubit

        # Store a representation of the circuit for ease of access.
        # Note that this representation does not account for any
        # standard parameters (i.e. those changed in the gate_set)
        # that are changed by the user.

        # This also ensures that the user has entered all necessary
        # data.
        if self.save_flag:
            user_data = [kwargs[kw]
                         for kw in self.gate_dic[gate_name]['user_kws']]
            if return_flag is not False:
                self.circuit_list.append((gate_name, *qubit_list,
                                          *user_data, return_flag))
            else:
                self.circuit_list.append((gate_name, *qubit_list,
                                          *user_data))

        # Get the gate to add to quantumsim.
        gate = self.gate_dic[gate_name]['function']

        # The save flag prevents saving multiple gate
        # definitions when using recursive gates (i.e.
        # gates that are decomposed and fed back to
        # the builder). We turn it off, and turn it on
        # after the execution of this gate if it was
        # previously on. As this could cause issues
        # when errors occur inserting the gate, we make
        # sure to turn it back afterwards regardless
        # of success.
        prev_flag = self.save_flag
        self.save_flag = False
        try:
            if isinstance(gate, str):
                self.circuit.add_gate(gate, **kwargs)

            elif isinstance(gate, type) and\
                    issubclass(gate, quantumsim.circuit.Gate):
                self.circuit.add_gate(gate(**kwargs))

            else:
                gate(builder=self, **kwargs)

            self.save_flag = prev_flag
        except:
            self.save_flag = prev_flag
            raise

        # Update time on qubits after gate is created
        # We do not do this if the user specifies the time as this
        # makes it impossible for us to properly account for the gate.
        if time_flag is False:
            for qubit in qubit_list:
                self.times[qubit] = max(self.times[qubit], time + gate_time)

        # My current best idea for adjustable gates - return the
        # gate that could be adjusted to the user.
        if return_flag is not False:
            return self.circuit.gates[-int(return_flag)]

    def update(self, **kwargs):
        for rule in self.update_rules:
            update_function_dic[rule](self, **kwargs)

    def finalize(self, topo_order=False, t_add=0):
        """
        Adds resting gates to all systems as required.
        quantumsim currently assumes fixed values for photon
        numbers, so we take them from a random qubit

        Photons in quantumsim are currently broken, so
        they're not in here right now.
        """

        circuit_time = max(self.times.values())
        if type(t_add) == dict:
            circuit_time = {key: val + circuit_time
                            for key, val in t_add.items()}
        else:
            circuit_time += t_add

        # args = list(self.qubit_dic.values())[0]

        # if 'photons' in args.keys() and args['photons'] is True:
        #     quantumsim.photons.add_waiting_gates_photons(
        #         self.circuit,
        #         tmin=0, tmax=circuit_time,
        #         alpha0=args['alpha0'], kappa=args['kappa'],
        #         chi=args['chi'])
        # else:

        self.circuit.add_waiting_gates(tmin=0, tmax=circuit_time)
        if topo_order is True:
            self.circuit.order()
        else:
            self.circuit.gates = sorted(self.circuit.gates,
                                        key=lambda x: x.time)
