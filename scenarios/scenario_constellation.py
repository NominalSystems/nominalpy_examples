# Advanced Constellation
from datetime import datetime

# Introduction
# This example showcases how the constellation utility functions can be leveraged to instantiate a constellation.
# In this example, a co-planar constellation of five spacecraft is created.
# Each spacecraft is initialised with a random pointing angle and then commanded to point consistently according to their local Local-Vertical, Local-Horizontal frame.

import numpy as np
import pandas as pd
from matplotlib import pyplot as plt

from nominalpy import types
from nominalpy.maths import astro, utils
from nominalpy.maths.constants import RPM
# from nominalpy.maths.utils import random_mrp
from nominalpy.maths.constellations import CoplanarCircular
from nominalpy import Simulation, Object

import credential_helper

# Scenario Configuration
# The scenario is configured with the following parameters:

# define the configuration of the scenario
num_spacecraft: int = 5
sma0: float = 7000e3  # the initial semi-major axis of the spacecraft's orbit, meters
inc0: float = np.radians(45)  # the initial inclination of the spacecraft's orbit, radians
raan0: float = np.radians(35)  # the initial right ascenscion of the ascending node of the spacecraft's orbit, radians

# Creating the Data Containers
# The components for each spacecraft can be stored in their own separate containers.
# By storing the component for each spacecraft, the component can be accessed later to connect messages and retrieve data.

# define the containers for the data for all of the spacecraft
ext_torque: list = []
spacecraft: list = []
navigators: list = []
attitude_tracking_error_fsws: list = []
mrp_feedback_fsws: list = []
lvlh_fsws: list = []
ephem_converter_fsws: list = []

# Simulation Authentication
# The simulation is authenticated using the credentials provided by Nominal Systems.
# The api key associated with this simulation can be created/found by creating an account on Nominal Systems' website.

# Construct the credentials
credentials = credential_helper.fetch_credentials()

# Create a simulation handle
simulation: Simulation = Simulation.get(credentials)

# Creating the Universe
# Every simulation has a universe object. We can configure the universe to have a specific epoch.

universe: Object = simulation.get_system(
    types.SOLAR_SYSTEM,
    Epoch=datetime(2021, 1, 15, hour=0, minute=28, second=30)
)

# The co-planar constellation utility class allows the user to calculate the initial state of the spacecraft equispaced about a single plane.
# The size and orientation of the orbital plane is defined by its semi-major axis, inclination, and right-ascension of the ascending node.
# Other orbital elements can further define the nature of the orbits and orbital plane, however are not included in this example.

# define a coplanar constellation of spacecraft using the utility function provided in nominalpy
cons = CoplanarCircular(
    semi_major_axis=sma0,
    inclination=inc0,
    right_ascension=raan0,
    argument_of_periapsis=np.radians(25),
    true_anomaly=0.0,
    num_satellites=num_spacecraft,
    init_classical_elements=True,
)


# The initial state of each spacecraft in the orbit can be returned as orbital elements or state vectors.
# They can also be calculated as osculating orbital values or the equivalent mean orbital elements/mean state vector.
# In this case we calculate the state vector directly in its osculating state.

# define a function to generate a random MRP vector for the initial attitude of the spacecraft

def random_mrp():
    """
    Generate a random MRP vector. This function generates a random MRP vector
    using the numpy random function. The MRP vector is generated by generating
    a random vector and normalizing it.

    :returns:   The random MRP vector
    :rtype:     np.ndarray
    """
    # Generate a random rotation axis (unit vector)
    axis: float = np.random.rand(3)
    axis /= np.linalg.norm(axis)

    # Generate a random rotation angle in radians
    angle: float = np.random.uniform(0, 2 * np.pi)

    # Convert angle-axis to quaternion
    q0: float = np.cos(angle / 2)
    q_vec: float = axis * np.sin(angle / 2)

    # Convert quaternion to MRP
    mrp = q_vec / (1 + q0)
    # return the random mrp
    return mrp


for _, vectors in cons.init_state_vectors_osculating(planet="earth").items():
    # create the spacecraft and initialise it with its orbit
    sc = simulation.add_object(
        types.SPACECRAFT,
        TotalMass=4.0,  # kg
        TotalCenterOfMassB_B=np.array((0, 0, 0)),
        TotalMomentOfInertiaB_B=np.diag([0.02 / 3.0, 0.1256 / 3.0, 0.1256 / 3.0]),  # kg m^2
        OverrideMass=True,  # When True, this forces a hard code of the total mass, com, and moi of the spacecraft
        Position=vectors["r_bn_n"],
        Velocity=vectors["v_bn_n"],
        # set default values, these will have to be updated for every test case
        Attitude=random_mrp(),
        AttitudeRate=np.array((0.0, 0.0, 0.0))
    )
    spacecraft.append(sc)

# configure the flight software on each spacecraft in the constellation
# Each spacecraft in the constellation is given a simple navigator software module which provides the spacecraft with
#   the current translational and rotational state.
# For example, the simple navigator is used to feed translational state data into the pointing mode flight software.
# In this example, each spacecraft in the constellation is set with an LVLH pointing mode dictated by the LVLH Pointing
#   Mode Flight Software.
# The attitude tracking error module is a flight software module that calculate the error between the current attitude
#   and the target attitude.
# This error is fed into a MRP Feedback Software module which is a PID controller that calculates the torque required
#   to bring the spacecraft to the target attitude.
# The external force torque module is used to apply the calculated torque to the spacecraft.

# set the flight software for every spacecraft in the constellation
for i, sc in enumerate(spacecraft):
    # set the navigation flight software
    # any software component is added to the spacecraft via the add_behaviour method instead of the add_child method
    #   as the software component is not a physical component of the spacecraft and has no mass, inertia, etc.
    navigators.append(
        sc.add_behaviour(
            "SimpleNavigationSoftware",
        )
    )
    # add the flight software to convert Earth location to a useable ephemeris
    ephem_converter_fsws.append(
        sc.add_behaviour(
            "PlanetEphemerisTranslationSoftware",
            In_SpicePlanetStateMsg=simulation.get_planet("Earth").get_message("Out_SpicePlanetStateMsg"),
        )
    )
    # add the LVLH reference frame flight software
    lvlh_fsws.append(
        sc.add_behaviour(
            "NadirPointingSoftware",
            In_NavigationTranslationMsg=navigators[i].get_message("Out_NavigationTranslationMsg"),
            In_EphemerisMsg=ephem_converter_fsws[i].get_message("Out_EphemerisMsg"),
        )
    )
    # add the tracking error software
    attitude_tracking_error_fsws.append(
        sc.add_behaviour(
            "AttitudeReferenceErrorSoftware",
            In_NavigationAttitudeMsg=navigators[i].get_message("Out_NavigationAttitudeMsg"),
            In_AttitudeReferenceMsg=lvlh_fsws[i].get_message("Out_AttitudeReferenceMsg"),
        )
    )
    # add the MRP feedback software
    ki = -1.0
    decay_time = 10.0
    xi = 1.0
    P = (0.1256 / 3) / decay_time
    mrp_feedback_fsws.append(
        sc.add_behaviour(
            "MRPFeedbackControlSoftware",
            K=(P / xi) * (P / xi) / (0.1256 / 3),
            P=P,
            Ki=ki,
            IntegralLimit=2.0 / ki * 0.1,
            In_AttitudeErrorMsg=attitude_tracking_error_fsws[i].get_message("Out_AttitudeErrorMsg").id,
            In_BodyMassMsg=sc.get_message("Out_BodyMassMsg").id,
        )
    )
    # connect the external force torque to the mrp feedback software
    # add the external force torque
    ext_torque.append(
        sc.add_child(
            "ExternalForceTorque",
            In_CommandTorqueMsg=mrp_feedback_fsws[i].get_message("Out_CommandTorqueMsg").id,
        )
    )

# subscribe to the messages
# The messages are subscribed to at a specific time step. This time step is the frequency at which data from messages
#   are recorded.
# Please note, that the messages will update within the simulation according to the tick size, however, but will only
#   be recorded and returned to users based at a frequency dictated by the subscribe step.

subscribe_step = 5.0
for k, sc in enumerate(spacecraft):
    simulation.set_tracking_interval(interval=subscribe_step)
    simulation.track_object(sc.get_message("Out_BodyMassMsg"))
    simulation.track_object(sc.get_message("Out_SpacecraftStateMsg"))
    simulation.track_object(attitude_tracking_error_fsws[k].get_message("Out_AttitudeErrorMsg"))
    simulation.track_object(mrp_feedback_fsws[k].get_message("Out_CommandTorqueMsg"))
    simulation.track_object(navigators[k].get_message("Out_NavigationAttitudeMsg"))

# run the scenario
# The scenario is run for a specific duration and time step.
# The duration is the total time the simulation will run for, and the time step is the frequency at which the
#   simulation will update the state of the spacecraft and all of its components and messages.

# run the scenario
simulation.tick_duration(time=400, step=0.1)

# Fetching and Analysing the Data
# The data from the simulation can be fetched and analysed. The data can be fetched as a dataframe and then analysed
#   using the pandas library.
# The data can be plotted to visualise the behaviour of the spacecraft.

# fetch the data as a dataframe and concatenate the frames into a single frame for each spacecraft
dfs_att = [simulation.query_dataframe(at.get_message("Out_AttitudeErrorMsg")) for at in attitude_tracking_error_fsws]
df_att0 = dfs_att[0]
df_body_state = pd.concat([simulation.query_dataframe(sc.get_message("Out_SpacecraftStateMsg")) for sc in spacecraft])
df_att = pd.concat(
    [simulation.query_dataframe(at.get_message("Out_AttitudeErrorMsg")) for at in attitude_tracking_error_fsws],
    keys=[i for i in range(len(attitude_tracking_error_fsws))]
)
# set the names of the indices
df_att.index = df_att.index.set_names(["sc_num", "index"])
df_att = df_att.reset_index(drop=False).set_index(["sc_num", "Time"]).drop(columns=["index"])

# If we plot the magnitude of the attitude tracking error for all spacecraft on one plot,
# we can see that the attitude of the spacecraft converges onto the target attitude for all spacecraft irrespective of
#   their initial attitude.

# plot the magnitude of the attitude tracking error for each spacecraft in the constellation
fig, ax = plt.subplots()
for j, sc in enumerate(spacecraft):
    ax.plot(
        df_att.loc[df_att.index.get_level_values("sc_num") == j].index.get_level_values("Time").values,
        np.linalg.norm(
            df_att.loc[df_att.index.get_level_values("sc_num") == j, ["Sigma_BR_0", "Sigma_BR_1", "Sigma_BR_2"]],
            axis=1
        ),
        label=f"Spacecraft {j + 1}"
    )
ax.set_title("Attitude Tracking Error")
ax.set_xlabel("Time [s]")
ax.set_ylabel("Attitude Error [MRP]")
ax.legend()
plt.show()
