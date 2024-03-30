from ngcsimlib.controller import Controller
from ngclearn.utils.io_utils import makedir
from ngclearn.utils.viz.raster import create_raster_plot
from ngclearn.utils.viz.synapse_plot import visualize
from jax import numpy as jnp, random
import time

class DC_SNN_Model():
    """
    Structure for constructing the spiking neural model proposed in:

    Diehl, Peter U., and Matthew Cook. "Unsupervised learning of digit recognition
    using spike-timing-dependent plasticity." Frontiers in computational
    neuroscience 9 (2015): 99.

    | Node Name Structure:
    | z0 -(W1)-> z1e <-(W1ie)- z1i ; z1i <-(W1ei)- z1e
    | Note: W1 = STDP-adapted synapses, W1ie and W1ei are fixed

    Args:
        dkey: JAX seeding key

        in_dim: input dimensionality

        hid_dim: dimensionality of the representation layer of neuronal cells

        T: number of discrete time steps to simulate neuronal dynamics

        dt: integration time constant

        exp_dir: experimental directory to save model results

        model_name: unique model name to stamp the output files/dirs with
    """
    # Define Functions
    def __init__(self, dkey, in_dim, hid_dim=100, T=200, dt=1., exp_dir="exp",
                 model_name="snn_stdp", **kwargs):
        self.exp_dir = exp_dir
        makedir(exp_dir)
        makedir(exp_dir + "/filters")
        makedir(exp_dir + "/raster")

        #T = 200 #250 # num discrete time steps to simulate
        self.T = T
        self.dt = dt
        tau_m_e = 100.500896468 # ms (excitatory membrane time constant)
        tau_m_i = 100.500896468 # ms (inhibitory membrane time constant)
        tau_tr= 20. # ms (trace time constant)

        ## STDP hyper-parameters
        Aplus = 1e-2 ## LTD learning rate (STDP); nu1
        Aminus = 1e-4 ## LTD learning rate (STDP); nu0

        #dkey = random.PRNGKey(1234)
        dkey, *subkeys = random.split(dkey, 10)

        ################################################################################
        ## Create model
        circuit = Controller()
        ### set up neuronal cells
        z0 = circuit.add_component("poiss", name="z0", n_units=in_dim, max_freq=63.75, key=subkeys[0])
        z1e = circuit.add_component("LIF", name="z1e", n_units=hid_dim, tau_m=tau_m_e, R_m=1.,
                                  thr=-52., v_rest=-65., v_reset=-60., tau_theta=1e7,
                                  theta_plus=0.05, refract_T=5., key=subkeys[2])
        z1i = circuit.add_component("LIF", name="z1i", n_units=hid_dim, tau_m=tau_m_i, R_m=1.,
                                  thr=-40., v_rest=-60., v_reset=-45., tau_theta=0.,
                                  one_spike=False, refract_T=5., key=subkeys[3])
        ### set up connecting synapses
        W1 = circuit.add_component("trstdp", name="W1", shape=(in_dim, hid_dim),
                                 eta=1., Aplus=Aplus, Aminus=Aminus, wInit=("uniform", 0.0, 0.3),
                                 w_norm=78.4, norm_T=T, preTrace_target=0., key=subkeys[1])
        # ie -> inhibitory to excitatory; ei -> excitatory to inhibitory (eta = 0 means no learning)
        W1ie = circuit.add_component("hebbian", name="W1ie", shape=(hid_dim, hid_dim),
                                   eta=0., wInit=("hollow", -120., 0.), w_bound=0., key=subkeys[4])
        W1ei = circuit.add_component("hebbian", name="W1ei", shape=(hid_dim, hid_dim),
                                   eta=0., wInit=("eye", 22.5, 0), w_bound=0., key=subkeys[5])
        ### add trace variables
        tr0 = circuit.add_component("trace", name="tr0", n_units=in_dim, tau_tr=tau_tr,
                                  decay_type="exp", a_delta=0., key=subkeys[6])
        tr1 = circuit.add_component("trace", name="tr1", n_units=hid_dim, tau_tr=tau_tr,
                                  decay_type="exp", a_delta=0., key=subkeys[7])

        ## wire up z0 to z1e with z0_z1 synapses
        circuit.connect(z0.name, z0.outputCompartmentName(),
                        W1.name, W1.inputCompartmentName()) ## z0 -> W1
        circuit.connect(W1.name, W1.outputCompartmentName(),
                        z1e.name, z1e.inputCompartmentName()) ## W1 -> z1e

        circuit.connect(z1i.name, z1i.outputCompartmentName(),
                        W1ie.name, W1ie.inputCompartmentName()) ## z1i -> W1ie
        circuit.connect(W1ie.name, W1ie.outputCompartmentName(),
                        z1e.name, z1e.inputCompartmentName(), bundle="fast_add") ## W1ie -> z1e
        circuit.connect(z1e.name, z1e.outputCompartmentName(),
                        W1ei.name, W1ei.inputCompartmentName()) ## z1e -> W1ei
        circuit.connect(W1ei.name, W1ei.outputCompartmentName(),
                        z1i.name, z1i.inputCompartmentName()) ## W1ei -> z1i

        # ## wire nodes z0 and z1e to their respective traces
        circuit.connect(z0.name, z0.outputCompartmentName(),
                        tr0.name, tr0.inputCompartmentName())
        circuit.connect(z1e.name, z1e.outputCompartmentName(),
                        tr1.name, tr1.inputCompartmentName())

        ## wire relevant compartment statistics to synaptic cable W1
        circuit.connect(tr0.name, tr0.traceName(),
                        W1.name, W1.presynapticTraceName())
        circuit.connect(tr1.name, tr1.traceName(),
                        W1.name, W1.postsynapticTraceName())
        circuit.connect(z0.name, z0.outputCompartmentName(),
                        W1.name, W1.inputCompartmentName())
        circuit.connect(z1e.name, z1e.outputCompartmentName(),
                        W1.name, W1.outputCompartmentName())
        ## checks that everything is valid within model structure
        #model.verify_cycle()

        ## make key commands known to model
        circuit.add_command("reset", command_name="reset",
                          component_names=[W1.name, W1ei.name, W1ie.name,
                                           z0.name, z1e.name, z1i.name,
                                           tr0.name, tr1.name],
                          reset_name="do_reset")
        circuit.add_command(
            "advance", command_name="advance",
            component_names=[W1.name, W1ie.name, W1ei.name, ## exec synapses first
                             z0.name, z1e.name, z1i.name, ## exec neuronal cells next
                             tr0.name, tr1.name ## exec traces last
                            ]
        )
        circuit.add_command("evolve", command_name="evolve",
                            component_names=[W1.name])
        circuit.add_command("clamp", command_name="clamp_input",
                                 component_names=[z0.name],
                                 compartment=z0.inputCompartmentName(),
                                 clamp_name="x")
        circuit.add_command("clamp", command_name="clamp_trigger",
                                 component_names=[W1.name], compartment=W1.triggerName(),
                                 clamp_name="trig")
        circuit.add_command("save", command_name="save",
                            component_names=[W1.name, z1e.name],
                            directory_flag="dir")

        ## tell model the order in which to run automatic commands
        # myController.add_step("clamp_input")
        circuit.add_step("advance")
        circuit.add_step("evolve")

        ## save JSON structure to disk once
        circuit.save_to_json(directory="exp", model_name=model_name)
        self.model_dir = "{}/{}/custom".format(exp_dir, model_name)
        circuit.save(dir=self.model_dir) ## save current parameter arrays
        self.circuit = circuit # embed circuit to model construct

    def save_to_disk(self):
        """
        Saves current model parameter values to disk
        """
        self.circuit.save(dir=self.model_dir) ## save current parameter arrays

    def load_from_disk(self):
        pass

    def viz_receptive_fields(self, fname, field_shape, show_stats=True):
        """
        Generates and saves a plot of the receptive fields for the current state
        of the model's synaptic efficacy values in W1.

        Args:
            fname: plot fname name (appended to end of experimental directory)

            field_shape: 2-tuple specifying expected shape of receptive fields to plot

            show_stats: display to I/O basic statistics of W1
        """
        _W1 = self.circuit.components.get("W1").weights
        visualize([_W1], [field_shape], self.exp_dir + "/filters/{}".format(fname))
        if show_stats == True:
            msg = "W1:\n  min {} \n  max {} \n  mu {} \n  norm {}"
            print(msg.format(jnp.amin(_W1),
                             jnp.amax(_W1),
                             jnp.mean(_W1),
                             jnp.linalg.norm(_W1)))

    def process(self, obs, adapt_synapses=True, collect_spike_train=False):
        """
        Processes an observation (sensory stimulus pattern) for a fixed
        stimulus window time T. Note that the observed pattern will be converted
        to a Poisson spike train with maximum frequency of 63.75 Hertz.

        Args:
            obs: observed pattern to have spiking model process

            adapt_synapses: if True, synaptic efficacies will be adapted in
                accordance with trace-based spike-timing-dependent plasticity

            collect_spike_train: if True, will store an T-length array of spike
                vectors for external analysis

        Returns:
            an array containing spike vectors (will be empty; length = 0 if
                collect_spike_train is False)
        """
        _S = []
        learn_flag = 0.
        if adapt_synapses == True:
            learn_flag = 1.
        self.circuit.reset(do_reset=True)
        for ts in range(1, self.T):
            self.circuit.clamp_input(obs) #x=inp)
            self.circuit.clamp_trigger(learn_flag)
            self.circuit.runCycle(t=ts*self.dt, dt=self.dt)

            if collect_spike_train == True:
                _S.append(self.circuit.components["z1e"].compartments["s"])
        return _S