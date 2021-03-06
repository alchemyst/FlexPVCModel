from __future__ import print_function
from tinydb import Query
from datahandling import my_query, access_db, extractnames
from itertools import combinations
from logging import debug, info
from sklearn.decomposition import PCA
from pca import pca_X

try:
    from winsound import Beep
except ImportError:
    def Beep(a, b):
        pass

from time import time
from sklearn.cross_validation import cross_val_score, ShuffleSplit
from sklearn.feature_selection import f_regression
from sklearn.linear_model import LinearRegression
from gen_model_inputs import get_all_lin_model_inp
from numpy import mean
Q = Query()

def gen_Y(db, equipment, data_type):
    """ Generates Y to for one equipment and data_type """
    data = db.search((Q.equipment_name == equipment) &
                     (Q.data_type == data_type))

    Y, sample_nos_Y = extractnames(data, 'value', 'sample_number')

    Y_scaled = [(2*(y - min(Y))/(max(Y) - min(Y)) - 1) for y in Y]
    
    return Y_scaled, sample_nos_Y

def gen_X(sample_numbers_Y, all_full_models, model_select_code):
    """ Generates X to score one model for one equipment and data_type """
    X = []
    for i in sample_numbers_Y:
        full_model_lin = all_full_models[i - 1]
            
        full_model_selected = [p for i, p in enumerate(full_model_lin) if i in model_select_code]
            
        X.append(full_model_selected)

    return X
    
def gen_terms_key():
    """ Generates the key to the model codes """
    terms_key = list(range(7))
    for i in combinations(list(range(7)), 2):
        terms_key.append(list(i))
    return terms_key

def my_sound():
    Beep(600,300)
    Beep(500,300)
    Beep(400,300)
    Beep(450,300)
    Beep(300,300)

def gen_all_possible_models(number_of_terms):
    """ Generates all the possible 2nd order Scheffe models
    up to a given number of model terms if up_to is True
    else only the number of terms """

    terms_key = gen_terms_key()

    cnt = 0
    t = time()

    db = access_db('All_Poss_Mod_{}_Terms'.format(number_of_terms), False)

    if db.contains(Q.is_complete == 'yes'):
        info('________________')
        info('Models with %d terms already done', number_of_terms)
        return

    n_models_done = len(db.all())
    cnt_mod = 0

    for i in combinations(list(range(28)), number_of_terms):
        invalid = False
        for j in i:
            if j >= 7:
                key_1 = terms_key[j][0]
                key_2 = terms_key[j][1]
                if key_1 not in i or key_2 not in i:
                    invalid = True
        
        if not invalid:
            cnt_mod += 1

        if not invalid and cnt_mod > n_models_done:
            db.insert({'mc': i})
            cnt += 1

    db.insert({'is_complete': 'yes'})

    info('________________')
    info('%d models with %d terms entered into DB', cnt, number_of_terms)
    req_time = time() - t
    minutes, seconds = divmod(req_time, 60)
    info('Required Time: %d min and %d s', round(minutes), round(seconds, 2))

def score_1_model(db, model, model_code, Y, sample_numbers_Y, all_full_models,
                  do_check=True):
    """ Scores one model to given Y and enters into scored models db """
    
    if do_check:
        done = db.contains((Q.model_code == model_code))
        if done:
            return

    X = gen_X(sample_numbers_Y, all_full_models, model_code)
    my_cv = ShuffleSplit(len(Y), n_iter=3, test_size=0.333, random_state=0)
    scores = cross_val_score(model, X, Y, cv=my_cv)

    entry = {'model_code': model_code,
             'n_terms': len(model_code),
             'kfold_score': mean(list(scores))
            }

    db.insert(entry)

def get_data_req_to_score_model():
    """ Calculates all the data required to run score_models_per_data_type
    that does not need to be recalculated in score_models_per_data_type """
    Q = Query()
  
    all_model_codes = []

    for i in range(28):
        number_of_terms = i + 1
        db = access_db(('All_Poss_Mod_{}_Terms'.format(number_of_terms)), False)

        all_model_codes += extractnames(db.search(Q.mc.exists()), 'mc')

    sv_db = access_db(0, True)
    model = LinearRegression(fit_intercept=False)
    all_full_models = get_all_lin_model_inp()
    return sv_db, model, all_full_models, all_model_codes
    
def score_models_per_data_type(edt):
    """ Fits all the models for a certain data type """
    sv_db, model, all_full_models, all_model_codes = get_data_req_to_score_model()
    
    equipment, data_type = edt
    
    db = access_db('Score_results_'+ equipment + '_' + data_type, False)
    
    Y, sn_Y = gen_Y(sv_db, equipment, data_type)
    
    for i in all_model_codes:
        model_code = i
        score_1_model(db, model, model_code, Y, sn_Y, all_full_models)
        
def score_model_per_comp(i):
    X, df = pca_X()
    my_pca = PCA(n_components=0.99)
    my_pca.fit(X)
    
    X_trans = my_pca.transform(X)
    sn_Y = list(df.index)
    Ys = map(list, zip(*X_trans))
    
    comp_no = i + 1
    Y = Ys[i]
    
    # Treat pca as equipment and component as data_type
    data_type = 'component_' + str(comp_no)
    equipment = 'pca'
    
    sv_db, model, all_full_models, all_model_codes = get_data_req_to_score_model()
    
    db = access_db('Score_results_'+ equipment + '_' + data_type, False)
    
    for model_code in all_model_codes:
        score_1_model(db, model, model_code, Y, sn_Y, all_full_models)