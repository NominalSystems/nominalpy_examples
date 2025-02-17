#!/usr/bin/env python3

'''
                    [ NOMINAL SYSTEMS ]
This code is developed by Nominal Systems to aid with communication 
to the public API. All code is under the the license provided along
with the 'nominalpy' module. Copyright Nominal Systems, 2024.

This example shows a spacecraft with a momentum management system that
is used to control the spacecraft's attitude. The spacecraft has a set
of reaction wheels and magnetic torque bars that are used to control
the spacecraft's attitude. The spacecraft is then controlled to point
at the sun.
'''

# Import the relevant helper scripts
import os, numpy as np
from datetime import datetime
from matplotlib import pyplot as plt
from nominalpy.maths import astro
from nominalpy import types, Object, Simulation, printer, System
from nominalpy.maths.constants import RPM
import credential_helper

# Clear the terminal
os.system('cls' if os.name == 'nt' else 'clear')

# Set the verbosity
printer.set_verbosity(printer.SUCCESS_VERBOSITY)



############################
# SIMULATION CONFIGURATION #
############################

# Create a simulation handle with the credentials
simulation: Simulation = Simulation.get(credential_helper.fetch_credentials())

# Configure the Universe with an epoch
solar_system: System = simulation.get_system(
    types.SOLAR_SYSTEM,
    Epoch=datetime(2022, 1, 1)
)

# Add the Earth's magnetic field
solar_system.invoke(
    "CreateMagneticFieldCenteredDipole",
    "earth",
    -15463,     # G10
    -1159,      # G11
    2908.5,     # H11
    -1,         # MinReach (not used)
    -1          # MaxReach (not used)
)

# Define the orbital elements
orbit: tuple = astro.classical_to_vector_elements_deg(
    semi_major_axis=6778.14 * 1000,     # meters
    eccentricity=0.0,
    inclination=45.0,                   # degrees
    right_ascension=60.0,               # degrees
    argument_of_periapsis=0.0,          # degrees
    true_anomaly=0.0                    # degrees
)

# Define the spacecraft with the current orbit
spacecraft: Object = simulation.add_object(
    types.SPACECRAFT,
    TotalMass=10.0,  # kg
    TotalCenterOfMassB_B=np.array([0, 0, 0]),
    TotalMomentOfInertiaB_B=np.array([
        [0.02 / 3.0, 0, 0],
        [0, 0.1256 / 3.0, 0],
        [0, 0, 0.1256 / 3.0]
    ]),
    Position=orbit[0],
    Velocity=orbit[1],
    Attitude=np.array([0.1, 0.2, -0.3]),
    AttitudeRate=np.array([0.001, -0.01, 0.03]),
    OverrideMass=True
)

# Add the magnetic torque bar array and reaction wheels, with four bars
mtb_array: Object = spacecraft.add_child("MagneticTorqueBarArray")
mtb_axes: list = [
    np.array([1, 0, 0]), 
    np.array([0, 1, 0]), 
    np.array([0, 0, 1]), 
    np.array([0.70710678, 0.70710678, 0.0])
]
for axis in mtb_axes:
    mtb = mtb_array.add_child(
        "MagneticTorqueBar",
        MaxDipoles=0.1,     # Am^2
        BarAxis_B=axis
    )

# Add the reaction wheels, with four wheels
reaction_wheels: Object = spacecraft.add_child("ReactionWheelArray")
RW_BETA = 52.0 * np.pi / 180.0
rw_axes: list = [
    np.array([0, np.cos(RW_BETA), np.sin(RW_BETA)]),
    np.array([0, np.sin(RW_BETA), -np.cos(RW_BETA)]),
    np.array([np.cos(RW_BETA), -np.sin(RW_BETA), 0]),
    np.array([-np.cos(RW_BETA), -np.sin(RW_BETA), 0])
]
for axis in rw_axes:
    reaction_wheels.add_child(
        "ReactionWheel",
        Mass=0.130,
        WheelPosition_B=np.array([0, 0, 0]),
        WheelSpinAxis_B=axis,
        WheelModelType="Balanced",
        Omega=0.0 * RPM,
        OmegaMax=5000.0 * RPM,
        MaxTorque=0.004,
        MinTorque=0.0,
        MaxMomentum=0.015,
        FrictionCoulomb=0.0,
        FrictionStatic=0.0,
        BetaStatic=-1.0,
        FrictionViscous=0.0,
        StaticImbalance=1.0E-7,
        DynamicImbalance=1.0E-8
    )

# Add the spacecraft's navigation software
navigator_fsw: Object = spacecraft.add_behaviour("SimpleNavigationSoftware")

# Add the spacecraft's magnetometer
tam: Object = spacecraft.add_child(
    "Magnetometer",
    NoiseStd=np.array([0.0, 0.0, 0.0])
)

# Add the inertial pointing software
inertial_hold_fsw: Object = spacecraft.add_behaviour(
    "InertialPointingSoftware",
    Sigma_RN=np.array([0.0, 0.0, 0.0])
)

# Add the attitude tracking error software
attitude_tracking_error_fsw: Object = spacecraft.add_behaviour(
    "AttitudeReferenceErrorSoftware",
    In_NavigationAttitudeMsg=navigator_fsw.get_message("Out_NavigationAttitudeMsg"),
    In_AttitudeReferenceMsg=inertial_hold_fsw.get_message("Out_AttitudeReferenceMsg")
)

# Add the MRP feedback control software
mrp_feedback_fsw: Object = spacecraft.add_behaviour(
    "MRPFeedbackControlSoftware",
    K=0.0001,
    P=0.002,
    Ki=-1.0,
    IntegralLimit=2.0 / -1.0 * 0.1,
    In_AttitudeErrorMsg=attitude_tracking_error_fsw.get_message("Out_AttitudeErrorMsg"),
    In_RWArraySpeedMsg=reaction_wheels.get_message("Out_RWArraySpeedMsg"),
    In_RWArrayConfigMsg=reaction_wheels.get_message("Out_RWArrayConfigMsg")
)

# Add the momentum management software
momentum_fsw: Object = spacecraft.add_behaviour(
    "RWMomentumControlSoftware",
    Kp=0.003,
    In_RWArrayConfigMsg=reaction_wheels.get_message("Out_RWArrayConfigMsg"),
    In_RWArraySpeedMsg=reaction_wheels.get_message("Out_RWArraySpeedMsg")
)

# Add the dipole mapping software
dipole_mapping_fsw: Object = spacecraft.add_behaviour(
    "MTBDipoleMappingSoftware",
    DipoleMapping=np.array([
        [0.75, -0.25, 0.0],
        [-0.25, 0.75, 0.0],
        [0.0, 0.0, 1.0],
        [0.35355339, 0.35355339, 0.0]
    ]),
)

# Add the feedforward mapping software
mtb_feedforward_fsw: Object = spacecraft.add_behaviour(
    "MTBFeedforwardMappingSoftware",
    In_DipoleArrayMsg=dipole_mapping_fsw.get_message("Out_DipoleArrayMsg"),
    In_CommandTorqueMsg=mrp_feedback_fsw.get_message("Out_CommandTorqueMsg"),
    In_MTBArrayConfigMsg=mtb_array.get_message("Out_MTBArrayConfigMsg")
)

# Add the reaction wheel torque mapping software
rw_motor_torque_fsw: Object = spacecraft.add_behaviour(
    "RWTorqueMappingSoftware",
    ControlAxes_B=np.eye(3),
    In_RWArrayConfigMsg=reaction_wheels.get_message("Out_RWArrayConfigMsg"),
    In_CommandTorqueMsg=mtb_feedforward_fsw.get_message("Out_CommandTorqueMsg")
)

# Add the reaction wheel null space software
rw_nullspace_fsw: Object = spacecraft.add_behaviour(
    "RWNullSpaceMappingSoftware",
    OmegaGain=0.000003,
    In_RWArrayConfigMsg=reaction_wheels.get_message("Out_RWArrayConfigMsg"),
    In_RWArraySpeedMsg=reaction_wheels.get_message("Out_RWArraySpeedMsg"),
    In_MotorTorqueArrayMsg=rw_motor_torque_fsw.get_message("Out_MotorTorqueArrayMsg")
)

# Add the TAM encoder software
tam_encoder_fsw: Object = spacecraft.add_behaviour(
    "TAMEncoderSoftware",
    In_TAMDataMsg=tam.get_message("Out_TAMDataMsg")
)

# Add the torque to dipole conversion software
torque_to_dipole_fsw: Object = spacecraft.add_behaviour(
    "TorqueDipoleConversionSoftware",
    In_TAMBodyMsg=tam_encoder_fsw.get_message("Out_TAMBodyMsg"),
    In_CommandTorqueMsg=momentum_fsw.get_message("Out_CommandTorqueMsg")
)

# Reconnect the messages for the other software
dipole_mapping_fsw.set(
    In_CommandDipoleMsg=torque_to_dipole_fsw.get_message("Out_CommandDipoleMsg"),
    In_MTBArrayConfigMsg=mtb_array.get_message("Out_MTBArrayConfigMsg")
)
mtb_feedforward_fsw.set(In_TAMBodyMsg=tam_encoder_fsw.get_message("Out_TAMBodyMsg"))

# Connect the messages for the MTB array and reaction wheels
mtb_array.set(In_DipoleArrayMsg=dipole_mapping_fsw.get_message("Out_DipoleArrayMsg"))
reaction_wheels.set(In_MotorTorqueArrayMsg=rw_nullspace_fsw.get_message("Out_MotorTorqueArrayMsg"))

# Set the data tracking interval for the simulation
simulation.set_tracking_interval(interval=60)

# Register data tracking for various messages from spacecraft components
simulation.track_object(reaction_wheels.get_message("Out_RWArraySpeedMsg"))
simulation.track_object(tam_encoder_fsw.get_message("Out_TAMBodyMsg"))
simulation.track_object(mtb_array.get_message("Out_MTBArrayNetTorqueMsg"))
simulation.track_object(torque_to_dipole_fsw.get_message("Out_CommandDipoleMsg"))

# Execute the simulation and tick
simulation.tick_duration(time=10000, step=1.0)



##############################
# DATA ANALYSIS AND PLOTTING #
##############################

# Create a figure with four plots, 2x2 grd as ax1, ax2, ax3, ax4
fig, axs = plt.subplots(2, 2, figsize=(12, 8))
fig.suptitle("Momentum Management System - MTBs & RWs", fontsize=16)

# Fetch the reaction wheel data and plot the wheel speeds for each of the four wheels
data_rw = simulation.query_dataframe(reaction_wheels.get_message("Out_RWArraySpeedMsg"))
axs[0, 0].plot(data_rw["Time"], data_rw["WheelSpeeds_0"], label="Wheel 1")
axs[0, 0].plot(data_rw["Time"], data_rw["WheelSpeeds_1"], label="Wheel 2")
axs[0, 0].plot(data_rw["Time"], data_rw["WheelSpeeds_2"], label="Wheel 3")
axs[0, 0].plot(data_rw["Time"], data_rw["WheelSpeeds_3"], label="Wheel 4")
axs[0, 0].set_title("Reaction Wheel Speeds")
axs[0, 0].set_ylabel("Speed [rad/s]")
axs[0, 0].legend()
axs[0, 0].grid(True)

# Plot the TAM body message from the encoder software
data_tam = simulation.query_dataframe(tam_encoder_fsw.get_message("Out_TAMBodyMsg"))
axs[0, 1].plot(data_tam["Time"], data_tam["Field_B_0"], label="X")
axs[0, 1].plot(data_tam["Time"], data_tam["Field_B_1"], label="Y")
axs[0, 1].plot(data_tam["Time"], data_tam["Field_B_2"], label="Z")
axs[0, 1].set_title("TAM Magnetic Field")
axs[0, 1].set_ylabel("Magnetic Field [T]")
axs[0, 1].legend()
axs[0, 1].grid(True)

# Plot the MTB net torque message
data_mtb = simulation.query_dataframe(mtb_array.get_message("Out_MTBArrayNetTorqueMsg"))
axs[1, 0].plot(data_mtb["Time"], data_mtb["NetTorque_B_0"], label="X")
axs[1, 0].plot(data_mtb["Time"], data_mtb["NetTorque_B_1"], label="Y")
axs[1, 0].plot(data_mtb["Time"], data_mtb["NetTorque_B_2"], label="Z")
axs[1, 0].set_title("MTB Net Torque")
axs[1, 0].set_xlabel("Time [s]")
axs[1, 0].set_ylabel("Torque [Nm]")
axs[1, 0].legend()
axs[1, 0].grid(True)

# Plot the dipole command message
data_dipole = simulation.query_dataframe(torque_to_dipole_fsw.get_message("Out_CommandDipoleMsg"))
axs[1, 1].plot(data_dipole["Time"], data_dipole["DipoleRequest_B_0"], label="X")
axs[1, 1].plot(data_dipole["Time"], data_dipole["DipoleRequest_B_1"], label="Y")
axs[1, 1].plot(data_dipole["Time"], data_dipole["DipoleRequest_B_2"], label="Z")
axs[1, 1].set_title("Dipole Command")
axs[1, 1].set_xlabel("Time [s]")
axs[1, 1].set_ylabel("Dipole [Am^2]")
axs[1, 1].legend()
axs[1, 1].grid(True)

# Show the plots
plt.tight_layout()
plt.show()