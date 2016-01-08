README

===================================
Intro
===================================
The purpose of the script is to run one or multiple processing jobs.

A processing job is defined as: processing data for all specified seasons with
a given set of parameters.
Example of a parameter: the number of games over which to calculate a
moving average.

Running multiple jobs lets you produce processed data with different
parameters to search for the ideal parameters.

===================================
OBJECT STRUCTURE
===================================
Major classes to be aware of:
- JobHandler: Creates a list of jobs with different params then executes them.
- Season: Contains and processes all data for a given season.
- Player, Team: Objects that contain all data associated with a given player
in a given season.
- Game: Looks up associated data for the players and teams for that game.
Collects it in one place.
- GameProcessor: Aggregates all data associated with one game into a single
row for output.
- DataProcessor objects: Handle all processing tasks related to a certain
type of data. Ie BoxscoreDataProcessor, ShotsDataProcessor

===================================
BASIC FLOW
===================================
1. Parameters specified in process_data.py.
2. JobHandler creates a list of jobs based on those parameters.
3. JobHandler performs those jobs one by one.
4. Within a job, JobHandler will iterate through the seasons specified by
that job.
5. For each season, a Season object is created.
6. Data is processed for that season, Player/Team/Game objects are created
within that season.
7. For each Game object, player/team/global/game variables are aggregated into
a row.
8. Each row is collected in one big list of rows corresponding to all games
played in all seasons.
9. This big list is converted into a pandas dataframe and dumped to disk.
10. On to the next job

===================================
FILE STRUCTURE
===================================
The big three files:
- process_data.py: Main file.
Specify params here and run this file to initiate a series of processing jobs.

- job_handler.py: Contains a JobHandler object which takes a set of params
specified in process_data.py and initiates a series of processing jobs.

- objects.py: Contains Season, Team, Player, Game objects.
The Season object contains a series of processing methods and sub-classes.
Team, Player, and Game objects represent teams, players, games within a specific
season and their associated data.

Also very important:
- helpers/processor.py: Contains DataProcessor objects, including
BoxscoreDataProcessor and ShotsDataProcessor. These Processor objects handle
all processing tasks.

JobHandler will create separate instances of each Processor objects for each
job, with different attributes depending on the parameters corresponding to each
job.

Modify this file if you want to change the way data is processed

Other stuff:
- helpers/calculators.py: Helper functions used to do stuff like calculate
advanced stats.
- helpers/utilities.py: Random helper functions.
- helpers/df_manipulators.py: Contains classes to do certain pandas dataframe
manipulation tasks, for example calculating rolling averages.
- helpers/loaders.py: Contains Loader and Slicer classes, used to load
pandas dataframes from disk and to slice for a specific season.