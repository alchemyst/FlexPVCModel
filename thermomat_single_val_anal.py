from __future__ import division
from __future__ import print_function

from datahandling import insert_update_db, my_query
from time import time as tm
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages
from lmfit import Parameters, minimize, report_fit
from thermomat_functions import cond_model, f2min, find_cut_point, rand_ini_val, parameters
from os import path
from numpy import trapz, log, abs
import matplotlib.pyplot as plt
from tinydb import Query
from equipment import Thermomat
from logging import debug, info

def thermomat_sva(db, redo):
    """ Setting redo = True will repeat analysis even if it has been done for that sample already
    The data in the data base will only be updated if the Error is less """
    
    equipment = Thermomat()

    Files = equipment.alldatafiles()
    
    t = tm()

    Q = Query()

    for j, f in enumerate(Files):
        split_tm = tm()
        
        # Parsing filename
        sample_number = equipment.file_parse(f)
        
        # Check if the relevant data exists and only do fit if necessary
        done = db.contains((Q.equipment_name == equipment.name)
                          & (Q.sample_number == int(sample_number)))

        if done and not redo:
            debug('Skipped Fit %d', (j + 1))
            continue

        # Get data
        time_data, conduct_data = equipment.simple_data(f)

        # Trim Data
        cut_point = find_cut_point(conduct_data)

        if cut_point is not None:
            time_data = time_data[:cut_point]
            conduct_data = conduct_data[:cut_point]

        # Remove offset
        min_cond = min(conduct_data)
        conduct_data[:] = [cond - min_cond for cond in conduct_data]

        # Find max conductivity to set upper limit of initial beta value
        max_cond = max(conduct_data)
        ini_val_up_lim = [50.0, 500.0, 3.0*max_cond, 1.5]

        # Fit Data with multiple starts
        starts = 10
        smallest_err = None

        for i in range(starts):
            ini_val = rand_ini_val(ini_val_up_lim)
            p0 = parameters(ini_val, ini_val_up_lim)
            result = minimize(f2min, p0, args=(time_data, conduct_data))
            p = result.params

            err = f2min(p, time_data, conduct_data)
            int_abs_err = trapz(abs(err), x=time_data)

            if smallest_err is None or int_abs_err < smallest_err:
                smallest_err = int_abs_err
                best_p = p

        # Entering info into tinydb
        # If previous value exist only update if err is less
        p_names = ['theta', 'tau', 'beta', 'm']
        values = [best_p[i].value for i in p_names]

        data_types = p_names
        data_types.append('int_of_abs_err')
        values.append(smallest_err)

        # Calculate and enter stability time
        # stability time used corresponds to the intercept
        # between the tangent line at the inflection point to the t axis
        theta = best_p['theta'].value
        tau = best_p['tau'].value

        stab_time = tau*(1 - (log(theta)/(theta - 1)))*((theta - 1)**(1/theta))
        data_types.append('stab_time_min')
        values.append(stab_time)
        
        if not done:
            insert_update_db(db, False, equipment.name, sample_number, data_types, values)
        else:
            old_err = db.search(my_query(equipment.name, sample_number, 'int_of_abs_err'))[0]['value']
            if smallest_err < old_err:
                insert_update_db(db, True, equipment.name, sample_number, data_types, values)
                debug('Updated Sample Number %s', sample_number)

        split_tm = tm() - split_tm
        debug('Completed Fit %d in %f (s)', (j + 1), round(split_tm, 2))

    req_time = tm() - t
    info('******************')
    info('Time required (min) = %f', round(req_time/60.0, 2))