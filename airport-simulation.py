# Simple Airport Simulation
# ISYE6501 Week 9 Assignment
# Oct 28, 2021
# nram@nram.dev

""""
Problem:
-----------------------------------------------------------------------
In this problem you, can simulate a simplified airport security system at a busy airport. 
Passengers arrive according to a Poisson distribution with λ1 = 5 per minute 
(i.e., mean interarrival rate 1 = 0.2 minutes) to the ID/boarding-pass check queue, 
where there are several servers who each have exponential service time with mean rate 2 = 0.75 minutes. 
After that, the passengers are assigned to the shortest of the several personal-check queues, 
where they go through the personal scanner (time is uniformly distributed between 0.5 minutes and 1 minute).

"""


# import required modules
import sys, os
import random
import simpy
from statistics import mean
import argparse
import pprint
from os.path import exists
pp = pprint.PrettyPrinter(indent=4)

# Globals
Verbose = 0 # turn on with -v option
Tracker = {} # global dictionary for keeping track of time
# system parameters
BoardingCheckRate = 0.75
PersScanningRateMin = 0.5
PersScanningRateMax = 1
# the following can be passed as run time args
NumRuns = 10
Duration = 60
NumPassengers = 5
NumCheckers = 2
NumScanners = 2

# ---------------------------------------------------------------------
# Airport class 
#
class Airport :
    # Constructor needs the SimPy environment
    def __init__(self, env, in_vars) :
        self.env = env
        self.in_vars = in_vars

        # Create queues (via a SimPy Resource)
        # single boarding check queue
        # multiple personal scanner queues
        self.boarding_queue = simpy.Resource(env, in_vars['numBoardingCheckers']) # One resource for ALL boarding_queue
        self.pers_scanners = []    # Empty array; one resource for each pers_scannerer (n-queues)
        for i in range(in_vars['numPersScanners']):
            self.pers_scanners.append(simpy.Resource(env,1)) # For each pers_scannerer, add a single resource

    # define how long a passenger gets to the checkout (exponential)
    def board_check_passenger(self, passenger_name):
        in_vars = self.in_vars
        yield self.env.timeout(random.expovariate(1.0/in_vars['boardingCheckRate']))

    # define how long a passenger takes to scan themselves in (uniform)
    def pers_scan_passenger(self, passenger_name):
        in_vars = self.in_vars
        yield self.env.timeout(random.uniform(in_vars['persScanningRateMin'], in_vars['persScanningRateMax']))

# ---------------------------------------------------------------------
# Passenger class
#
class Passenger:
    def __init__(self, env, name, airport):
        self.env = env
        self.name = name 
        self.airport = airport 

    def checkin(self):
        global Tracker

        env = self.env 
        name = self.name 
        airport = self.airport 

        # We need to calculate all metrics that we want to track
        arrival_time = env.now    #  time the passenger arrives
        boarding_check_wait_time = 0     # Wait time for a boarding check station
        boarding_check_time = 0    # Time spent getting passenger checked @ ID/boarding station
        pers_scanning_wait_time = 0      # Wait time for the pers scanner station
        pers_scanning_time = 0     # Time spent getting passenger scanned

        # Passenger first goes through the single board_check station queue
        # Just need to 'request' (SimPy) a resource 
        with airport.boarding_queue.request() as request:
            # Request a board_check station
            yield request

            # Note the start time
            start_time = env.now

            # Wait time is start time - arrival time
            boarding_check_wait_time = start_time-arrival_time

            # Board the passenger
            yield env.process(airport.board_check_passenger(name))

            # Save the time spent in the board_check queue
            boarding_check_time = env.now - start_time

        pers_scan_arrival_time = env.now 

        # Now passenger randomly gets assigned to one of the pers_scanner stations
        pers_scan_station = random.randint(0,airport.in_vars['numPersScanners']-1)
        with airport.pers_scanners[pers_scan_station].request() as request:
            yield request
            start_time = env.now
            pers_scanning_wait_time = start_time - pers_scan_arrival_time
            yield env.process(airport.pers_scan_passenger(name))
            pers_scanning_time = env.now-start_time
        
        # save metrics
        Tracker['boardingCheck'].append([boarding_check_wait_time, boarding_check_time])
        Tracker['persScan'].append([pers_scanning_wait_time, pers_scanning_time])
        Tracker['totalTime'].append(env.now - arrival_time)

        # passenger is out of the system now.


# ---------------------------------------------------------------------
# AirportSimulation call
# Orchestrates the simulation
#
class AirportSimulation:
    def __init__(self, id, in_vars):
        global Tracker

        # Create a SimPy environment
        env = simpy.Environment()
        self.id = id
        self.env = env
        self.in_vars = in_vars
        self.stats = {}

        # reset globals between runs
        self.total_passengers = 0  
        Tracker['boardingCheck'] = []
        Tracker['persScan'] = []  
        Tracker['totalTime'] = [] 

        # Start the simulation by having passengers arrive  
        self.airport = Airport(env, in_vars)
        self.stats_file = 'simulation-stats.csv'

        # Run the simulation for specified duration
        env.process(self.run())
        env.run(in_vars['simulationTimeLimit'])

    # This function defines how passengers arrive
    def run(self):
        # globals

        env = self.env
        airport = self.airport
        in_vars = self.in_vars

        # Internal tracker for each run
        num_passengers = 0

        while True:
            # Simulate arrival time
            yield env.timeout(random.expovariate(1.0/in_vars['passengerArrivalRate']))

            # Increment the number of passengers
            num_passengers += 1
            self.total_passengers += 1

            # After simulating the arrival time, create a passenger using Simpy "process"
            passenger_uid = f'Passenger {num_passengers}'
            passenger = Passenger(env, passenger_uid, airport)
            env.process( passenger.checkin())

    # calcuate stats      
    def get_stats(self) :
        stats = self.stats
        stats['TotalPassengers'] = self.total_passengers
        stats['AvgBoardingCheckWaitTime'] = mean(list(zip(*Tracker['boardingCheck']))[0])
        stats['AvgBoardingCheckTime'] = mean(list(zip(*Tracker['boardingCheck']))[1])
        stats['AvgPersScanWaitTime'] = mean(list(zip(*Tracker['persScan']))[0])
        stats['AvgPersScanTime'] = mean(list(zip(*Tracker['persScan']))[1])
        stats['AvgTimeAtAirport'] = mean(Tracker['totalTime'])
        stats['AvgWaitTime'] =  stats['AvgBoardingCheckWaitTime'] + stats['AvgPersScanWaitTime']
        return stats

#--------------------------------------------------------------------
# Main Class - wrapper for everything
#
class Main :

    def __init__(self, argv):
        global Verbose

        # parse args
        p = argparse.ArgumentParser()
        p.add_argument('-n', '--num-runs',       help='Replication count', type=int, default = NumRuns) 
        p.add_argument('-t', '--duration',       help='Simulation time',  type=int, default = Duration) 
        p.add_argument('-p', '--num-passengers', help='Number of passengers per min', type=int, default = NumPassengers)
        p.add_argument('-c', '--num-checkers',   help='Number of boarding checkers', type=int, default = NumCheckers)
        p.add_argument('-s', '--num-scanners',   help='Number of self scanners', type=int, default = NumScanners)
        p.add_argument('-v', '--verbose',        help='Verbose output', action="count", required=False, default=0 )
        r = p.parse_args()
        Verbose = r.verbose
        self.r = r
        self.all_stats = [] # store stats from all runs
        self.stats_file = 'avg-simulation-stats.csv'
        self.in_vars = self.input_vars()

        # run simulation
        self.run()

        # process stats
        self.avg_stats = self.get_avg_stats()
        self.write_stats(self.avg_stats)
        self.print_input_vars()
        self.print_stats(self.avg_stats)

    # generate a random set of reasonable parameters to run simulation
    def input_vars (self):
        r = self.r
        in_vars = {}
        in_vars['numBoardingCheckers'] = r.num_checkers
        in_vars['numPersScanners'] = r.num_scanners
        in_vars['passengerArrivalRate'] = 1.0/r.num_passengers
        in_vars['boardingCheckRate'] = BoardingCheckRate
        in_vars['persScanningRateMin'] = PersScanningRateMin
        in_vars['persScanningRateMax'] = PersScanningRateMax
        in_vars['simulationTimeLimit'] = self.r.duration
        return in_vars

    def print_input_vars(self):
        in_vars = self.in_vars
        print ('Input Variables')
        print ('   {:40s} : {}'. format('numRuns', self.r.num_runs))
        for k in in_vars.keys():
            print ('   {:40s} : {}'. format(k, in_vars[k]))
    
    # now run simulation N times
    def run(self):
        n = self.r.num_runs
        for i in range(n):
            print (f"Simulation run {i} / {n}")
            sim = AirportSimulation(i, self.in_vars)
            sim.run()
            self.all_stats.append(sim.get_stats())
            #if Verbose:
            #    sim.print_stats()
            #sim.write_stats()

    # get average for each stats from all runs
    def get_avg_stats (self):
        n = self.r.num_runs
        stats = self.all_stats
        print (f'Getting average stats from all {n} runs')
        #pp.pprint(stats)
        avg_stats = {}
        for k in stats[0].keys():
            avg_stats[k] = sum([ s[k] for s in stats ])/n
        return avg_stats

    # write stats to file for further processing
    def write_stats(self, stats):
        in_vars = self.in_vars
        write_hdr = False
        if not exists(self.stats_file):
            write_hdr = True
        print (f'Adding stats to {self.stats_file}')
        with open(self.stats_file, 'a') as f:
            # write header first time
            if write_hdr:
                f.write("nruns")
                for key in sorted(in_vars.keys()):
                    f.write(",%s" % key)
                for key in sorted(stats.keys()):
                    f.write(",%s" % key)
                f.write('\n')

            f.write("%d" % self.r.num_runs)
            # write the input_vars
            for key in sorted(in_vars.keys()):
                f.write(",%s" % in_vars[key])
            # write the stats
            for key in sorted(stats.keys()):
                f.write(",%s"%(stats[key]))
            f.write('\n')

    # print stats to screen
    def print_stats(self, stats):
        print ('Avg. Simulation Stats:')
        for t in stats:
            print ('   {:40s} : {}'. format(t, stats[t]))

# ---------------------------------------------------------------------------
# program entry point
# 
if __name__ == "__main__":
    """ program entry point - must be  below main() """
    Main(sys.argv[1:]) 
