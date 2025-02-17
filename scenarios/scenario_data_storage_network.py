#!/usr/bin/env python3

'''
                    [ NOMINAL SYSTEMS ]
This code is developed by Nominal Systems to aid with communication 
to the public API. All code is under the the license provided along
with the 'nominalpy' module. Copyright Nominal Systems, 2024.

This example shows a spacecraft with a data storage network that is
used to store data from a ground station. The spacecraft has a receiver
and the ground station has a transmitter. The transmitter sends data to
the receiver, which is then stored in the spacecraft's data storage.
'''

# Import the relevant helper scripts
import os, numpy as np, pytz
import matplotlib.pyplot as plt
from datetime import datetime
from nominalpy.maths import astro
from nominalpy import types, System, Simulation, printer
from nominalpy.maths.constants import RPM
from nominalpy.maths.data import kilobytes_to_bits, megabytes_to_bytes, kilobytes_to_bytes, gigabytes_to_bytes
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

# Define the epoch and set the solar system time
epoch = datetime(2022, 1, 1, tzinfo=pytz.utc)
solar_system: System = simulation.get_system(
    types.SOLAR_SYSTEM,
    Epoch=epoch
)

# Add the ground station with the necessary components
LATITUDE: float = 2.0
LONGITUDE: float = 170.0
ALTITUDE: float = 0.0
ground_station = simulation.add_object(
    types.GROUND_STATION,
    MinimumElevation=30.0,
    MaximumRange=2000000.0,
    Latitude=LATITUDE,
    Longitude=LONGITUDE,
    Altitude=ALTITUDE
)

# Define the classic orbital elements
orbit: tuple = astro.classical_to_vector_elements_deg(
    semi_major_axis=8000*1000,      # m
    eccentricity=0.0,
    inclination=25.0,               # deg
    right_ascension=90.0,           # deg
    argument_of_periapsis=0.0,      # deg
    true_anomaly=160.0              # deg
)

# Define the spacecraft properties
spacecraft = simulation.add_object(
    types.SPACECRAFT,
    TotalMass=750.0,  # kg
    TotalCenterOfMassB_B=np.array([0, 0, 0], dtype=np.float64),  # m
    TotalMomentOfInertiaB_B=np.diag([900.0, 800.0, 600.0]),  # kg m^2
    Position=orbit[0],
    Velocity=orbit[1],
    Attitude=np.array((0.1, 0.2, -0.3)),  # MRP
    AttitudeRate=np.array((0.001, -0.001, 0.001)),  # rad/s
)

# Add the groundstation components to the spacecraft
receiver = ground_station.add_child(
    "Receiver",
    Frequency=1000 * 1e6,
)

# Add the data storage system
ground_station_data_storage = ground_station.add_child(
    "PartitionedDataStorage",
    Capacity=megabytes_to_bytes(1.0)
)

# Add in the data manager
ground_storage_manager = ground_station_data_storage.add_behaviour(
    "DataStorageMessageWriter"
)

# Create the receiver storage model
receiver_storage = receiver.get_model(
    "ReceiverMessageWriterModel",
    Storage=ground_station_data_storage
)

# Create the reaction wheel array
reaction_wheels = spacecraft.add_child("ReactionWheelArray")

# Create the reaction wheels - one in each axis
for axis in [np.array([1, 0, 0]), np.array([0, 1, 0]), np.array([0, 0, 1])]:
    reaction_wheels.add_child(
        "ReactionWheel",
        Mass=9.0,
        WheelPosition_B=np.array([0.0, 0.0, 0.0]),
        WheelSpinAxis_B=axis,
        WheelModelType="Balanced",
        Omega=100.0 * RPM,
        OmegaMax=6000.0 * RPM,
        MaxTorque=0.2,
        MinTorque=0.00001,
        MaxMomentum=50.0,
        FrictionCoulomb=0.000,
        FrictionStatic=0.0,
        BetaStatic=-1.0,
        StaticImbalance=0.0,
        DynamicImbalance=0.0,
    )

# Add the transmitter
transmitter = spacecraft.add_child(
    "Transmitter",
    Frequency=1000 * 1e6,
    BaudRate=16000,
    PacketSize=kilobytes_to_bits(1.0)
)

# Add the data storage system
spacecraft_data_storage = spacecraft.add_child(
    "PartitionedDataStorage",
    Capacity=kilobytes_to_bytes(100)
)

# Add in the data manager
sc_storage_manager = spacecraft_data_storage.add_behaviour(
    "DataStorageMessageWriter",
    WriteInterval=10.0
)

# Create the transmitter storage model
transmitter_storage = transmitter.get_model(
    "TransmitterStorageModel",
    MessageWriter=sc_storage_manager
)

# Add the operation computer
computer = spacecraft.add_child(
    "SpacecraftOperationComputer",
    PointingMode="Nadir",
    ControllerMode="MRP"
)

# Sync the clock with the current time of the simulation from the sun
computer.invoke("SyncClock", solar_system.get("Epoch"))

# Track the spacecraft and link access message to transmitter storage
access_msg = ground_station.invoke("TrackObject", spacecraft)
transmitter_storage.set(In_AccessMsg=access_msg)

# Track the messages with the storage system
sc_storage_manager.invoke("RegisterMessage", access_msg)
sc_storage_manager.invoke("RegisterMessage", computer.get_message("Out_NavigationAttitudeMsg"))
sc_storage_manager.invoke("RegisterMessage", computer.get_message("Out_NavigationTranslationMsg"))

# Subscribe to the data
simulation.track_object(reaction_wheels.get_message("Out_RWArraySpeedMsg"))
simulation.track_object(spacecraft_data_storage.get_message("Out_DataStorageMsg"))
simulation.track_object(transmitter)
simulation.track_object(receiver)

# Run the simulation for the defined duration
simulation.tick_duration(step=0.1, time=720)



##############################
# DATA ANALYSIS AND PLOTTING #
##############################

# Create a figure with four plots, 2x2 grd as ax1, ax2, ax3, ax4
fig, axs = plt.subplots(2, 2, figsize=(12, 8))
fig.suptitle("Data Storage Network", fontsize=16)

# Fetch the storage data from the simulation and plot the allocated data
data_storage = simulation.query_dataframe(spacecraft_data_storage.get_message("Out_DataStorageMsg"))
axs[0, 0].plot(data_storage["Time"], data_storage["Allocated"], label="Allocated Data")
axs[0, 0].plot(data_storage["Time"], data_storage["Capacity"], label="Capacity")
axs[0, 0].set_title("Data Storage")
axs[0, 0].set_ylabel("Data [B]")
axs[0, 0].legend()
axs[0, 0].grid(True)

# Fetch the transmitter data from the simulation and plot the data transmitted
data_transmitter = simulation.query_dataframe(transmitter)
axs[0, 1].plot(data_transmitter["Time"], data_transmitter["BytesTransmitted"], label="Data Transmitted")
axs[0, 1].set_title("Bytes Transmitted")
axs[0, 1].set_ylabel("Data [B]")
axs[0, 1].grid(True)

# Fetch the reaction wheel data from the simulation and plot the speed
data_rw = simulation.query_dataframe(reaction_wheels.get_message("Out_RWArraySpeedMsg"))
for i in range(3):
    axs[1, 0].plot(data_rw["Time"], data_rw[f"WheelSpeeds_{i}"], label=f"Wheel {i + 1}")
axs[1, 0].set_title("Reaction Wheel Speed")
axs[1, 0].set_ylabel("Speed [rad/s]")
axs[1, 0].set_xlabel("Time [s]")
axs[1, 0].legend()
axs[1, 0].grid(True)

# Plot the signal to noise from the receiver
data_receiver = simulation.query_dataframe(receiver)
axs[1, 1].plot(data_receiver["Time"], data_receiver["SignalToNoise"], label="Signal to Noise")
axs[1, 1].set_title("Signal to Noise")
axs[1, 1].set_ylabel("SNR [dB]")
axs[1, 1].set_xlabel("Time [s]")
axs[1, 1].grid(True)

# Show the plots
plt.tight_layout()
plt.show()
exit()