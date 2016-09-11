# -*- coding: utf-8 -*-
"""
Created on Thu Sep  8 15:27:30 2016

@author: bbalasub
"""
import scipy
import scipy.interpolate

def glmnetPredict(fit,\
                  newx = scipy.empty([0]), \
                  s = scipy.empty([0]), \
                  ptype = 'link', \
                  exact = False, \
                  offset = scipy.empty([0])):
    
    typebase = ['link', 'response', 'coefficients', 'nonzero', 'class']
    indxtf   = [x.startswith(ptype.lower()) for x in typebase]
    indl     = [i for i in range(len(indxtf)) if indxtf[i] == True]
    ptype = typebase[indl[0]]
    
    if len(newx) == 0 and ptype != 'coefficients' and ptype != 'nonzero':
        raise ValueError('You need to supply a value for ''newx''')
    
    # python 1D arrays are not the same as matlab 1xn arrays
    # check for this. newx = x[0:1, :] is a python 2D array and would work; 
    # but newx = x[0, :] is a python 1D array and should not be passed into 
    # glmnetPredict    
    if len(newx.shape) == 1 and newx.shape[0] > 0:
        raise ValueError('newx must be a 2D (not a 1D) python array')
   
    if exact == True and len(s) > 0:
        # It is very messy to go back into the caller namespace
        # and call glmnet again. The user should really do this at their end
        # by calling glmnet again using the correct array of lambda values that
        # includes the lambda for which prediction is sought
        raise NotImplementedError('exact = True option is not implemented in python')
    
    # elnet
    if fit['class'] in ['elnet', 'fishnet', 'lognet']:
        if fit['class'] == 'lognet':
            a0 = fit['a0']
        else:    
            a0 = scipy.transpose(fit['a0'])
        
        a0 = scipy.reshape(a0, [1, a0.size])   # convert to 1 x N for appending
        nbeta = scipy.append(a0, fit['beta'], axis = 0)        
        if scipy.size(s) > 0:
            lambdau = fit['lambdau']
            lamlist = lambda_interp(lambdau, s)
            nbeta = nbeta[:, lamlist['left']]*scipy.tile(scipy.transpose(lamlist['frac']), [nbeta.shape[0], 1]) \
            + nbeta[:, lamlist['right']]*( 1 - scipy.tile(scipy.transpose(lamlist['frac']), [nbeta.shape[0], 1]))
            
        if ptype == 'coefficients':
            result = nbeta
            return(result)
            
        if ptype == 'nonzero':
            result = nonzeroCoef(nbeta[1:nbeta.shape[0], :], True)
            return(result)
        result = scipy.dot(scipy.append(scipy.ones([newx.shape[0], 1]) \
                              , newx, axis = 1) , nbeta)
        if fit['offset']:
            if len(offset) == 0:
                raise ValueError('No offset provided for prediction, yet used in fit of glmnet')                              
            if offset.shape[1] == 2:
                offset = offset[:, 1]
                
            result = result + scipy.tile(offset, [1, result.shape[1]])    

    # fishnet                
    if fit['class'] == 'fishnet' and ptype == 'response':
        result = scipy.exp(result)

    # lognet
    if fit['class'] == 'lognet':
        if ptype == 'response':
            pp = scipy.exp(-result)
            result = 1/(1 + pp)
        elif ptype == 'class':
            result = (result > 0)*1 + (result <= 0)*0
            result = fit['label'][result]

    # multnet / mrelnet
    if fit['class'] == 'mrelnet':
        if type == 'response':
            ptype = 'link'
        fit['grouped'] = True
        
        a0 = fit['a0']
        nbeta = fit['beta']
        nclass = a0.shape[0]
        nlambda = s.size
        
        if len(s) > 0:
            lambdau = fit['lambdau']
            lamlist = lambda_interp(lambdau, s)
            for i in range(nclass):
                kbeta = scipy.append(a0[i, :], nbeta[i], axis = 0)
                kbeta = kbeta[:, lamlist['left']]*scipy.tile(scipy.transpose(lamlist['frac']), [kbeta.shape[0], 1]) \
                        + kbeta[:, lamlist['right']]*( 1 - scipy.tile(scipy.transpose(lamlist['frac']), [kbeta.shape[0], 1]))
                nbeta[i] = kbeta
        else:
            for i in range(nclass):
                nbeta[i] = scipy.append(a0[i, :], nbeta[i], axis = 0)
            nlambda = len(fit['lambda'])    

        if ptype == 'coefficients':
            result = nbeta
            return(result)
            
        if ptype == 'nonzero':
            if fit['grouped']:
                result = list()
                tn = nbeta[0].shape[0]
                result.append(nonzeroCoef(nbeta[0][1:tn, 0:1], True))
            else:
                result = list()
                for i in range(nclass):
                    tn = nbeta[0].shape[0]
                    result.append(nonzeroCoef(nbeta[0][1:tn, 0:1], True))  
            return(result)
            
        npred = newx.shape[0]
        dp = scipy.zeros([nclass, nlambda, npred], dtype = scipy.float64)
        for i in range(nclass):
            fitk = scipy.dot( scipy.append(scipy.ones([newx.shape[0], 1]), newx, axis = 1), nbeta[i] )
            dp[i, :, :] = dp[i, :, :] + scipy.reshape(scipy.transpose(fitk), [1, nlambda, npred])

        if fit['offset']:
            if len(offset) == 0:
                raise ValueError('No offset provided for prediction, yet used in fit of glmnet')
            if offset.shape[1] != nclass:
                raise ValueError('Offset should be dimension %d x %d' % (npred, nclass))
            toff = scipy.transpose(offset)
            for i in range(nlambda):
                dp[:, i, :] = dp[:, i, :] + toff
                
            if ptype == 'response':
                pp = scipy.exp(dp)
                psum = scipy.sum(pp, axis = 0)
                result = scipy.transpose(pp/scipy.tile(psum, [nclass, 1]), [2, 0, 1])
            if ptype == 'link':
                result = scipy.transpose(dp, [2, 0, 1])
            if ptype == 'class':
                dp = scipy.transpose(dp, [2, 0, 1])
                result = scipy.empty([0])
                for i in range(dp.shape[2]):
                    result = scipy.append(result, fit['label'][softmax(dp[:, :, i])])

    # coxnet
    if fit['class'] == 'coxnet':
        nbeta = fit['beta']        
        if len(s) > 0:
            lambdau = fit['lambdau']
            lamlist = lambda_interp(lambdau, s)
            nbeta = nbeta[:, lamlist['left']]*scipy.tile(scipy.transpose(lamlist['frac']), [nbeta.shape[0], 1]) \
            + nbeta[:, lamlist['right']]*( 1 - scipy.tile(scipy.transpose(lamlist['frac']), [nbeta.shape[0], 1]))
            
        if ptype == 'coefficients':
            result = nbeta
            return(result)
            
        if ptype == 'nonzero':
            result = nonzeroCoef(nbeta, True)
            return(result)
        
        result = scipy.dot(newx * nbeta)
        
        if fit['offset']:
            if len(offset) == 0:
                raise ValueError('No offset provided for prediction, yet used in fit of glmnet')                              

            result = result + scipy.tile(offset, [1, result.shape[1]])    
        
        if ptype == 'response':
            result = scipy.exp(result)

    return(result)
    
# end of glmnetPredict
# =========================================    


# =========================================
# helper functions
# =========================================    
def lambda_interp(lambdau, s):
# lambda is the index sequence that is produced by the model
# s is the new vector at which evaluations are required.
# the value is a vector of left and right indices, and a vector of fractions.
# the new values are interpolated bewteen the two using the fraction
# Note: lambda decreases. you take:
# sfrac*left+(1-sfrac*right)
    if len(lambdau) == 1:
        nums = len(s)
        left = scipy.zeros([nums, 1], dtype = scipy.integer)
        right = left
        sfrac = scipy.zeros([nums, 1], dtype = scipy.float64)
    else:
        s[s > scipy.amax(lambdau)] = scipy.amax(lambdau)
        s[s < scipy.amin(lambdau)] = scipy.amin(lambdau)
        k = len(lambdau)
        sfrac = (lambdau[0] - s)/(lambdau[0] - lambdau[k - 1])
        lambdau = (lambdau[0] - lambdau)/(lambdau[0] - lambdau[k - 1]) 
        coord = scipy.interpolate.interp1d(lambdau, range(k))(sfrac)
        left = scipy.floor(coord).astype(scipy.integer, copy = False)
        right = scipy.ceil(coord).astype(scipy.integer, copy = False)
        if left != right:
            sfrac = (sfrac - lambdau[right])/(lambdau[left] - lambdau[right])
        else:
            sfrac[left == right] = 1.0
    result = dict()    
    result['left'] = left
    result['right'] = right
    result['frac'] = sfrac
    
    return(result)
# end of lambda_interp    
# =========================================    
def softmax(x, gap = False):
   d = x.shape
   maxdist = x[:, 0]
   pclass = scipy.ones([d[0], 1], dtype = scipy.integer)
   for i in range(1, d[1], 1):
       l = x[:, i] > maxdist
       pclass[l] = i
       maxdist[l] = x[l, i]
   if gap == True:
       x = scipy.absolute(maxdist - x)
       x[0:d[0], pclass] = x*scipy.ones([d[1], d[1]])
       #gaps = pmin(x)# not sure what this means; gap is never called with True
       raise ValueError('gap = True is not implemented yet')
    
   result = dict()
   if gap == True:
       result['pclass'] = pclass
       #result['gaps'] = gaps
       raise ValueError('gap = True is not implemented yet')
   else:
       result['pclass'] = pclass;
  
   return(result)
# end of softmax
# =========================================    
def nonzeroCoef(beta, bystep = False):
    result = scipy.absolute(beta) > 0
    if not bystep:
        result = scipy.any(result, axis = 1)
    return(result)    
# end of nonzeroCoef
# =========================================    
     