# I'm imagineing some class to plot results and compare model to data
# In imcascade the results class injests the fitter class which works well I think but definetly open to suggestions.
import matplotlib.pyplot as plt
from typing import Callable, Optional, Union
import numpyro 
import jax 
from jax import random 
import pandas 
import numpy as np 
from mpl_toolkits.axes_grid1.axes_divider import make_axes_locatable
import corner
import jax.numpy as jnp
import arviz as az 
ArrayLike = Union[np.array, jax.numpy.array]
from pysersic.rendering import (
    BaseRenderer,
    FourierRenderer,
    HybridRenderer,
)
from pysersic.utils import gaussian_loss, train_numpyro_svi_early_stop 



class PySersicResults():
    def __init__(self,
                data: ArrayLike,
                rms: ArrayLike,
                psf: ArrayLike,
                mask: Optional[ArrayLike] = None,
                loss_func: Optional[Callable] = gaussian_loss,
                renderer: Optional[BaseRenderer] =  HybridRenderer,):
        self.data = data 
        self.rms = rms 
        self.psf = psf 
        self.mask = mask 
        self.loss_func = loss_func 
        self.renderer = renderer

    def add_prior(self,prior):
        self.prior = prior 
    def injest_data(self, 
                sampler: Optional[numpyro.infer.mcmc.MCMC] =  None, 
                svi_res_dict: Optional[dict] =  None,
                purge_extra: Optional[bool] = True,
                rkey: Optional[jax.random.PRNGKey] = random.PRNGKey(5)
        ) -> pandas.DataFrame:
        """Method to injest data from optimized SVI model or results of sampling. Sets the class attribute 'idata' with an Arviz InferenceData object.

        Parameters
        ----------
        sampler : Optional[numpyro.infer.mcmc.MCMC], optional
            numpyro sampler containing results
        svi_res_dict : Optional[dict], optional
            Dictionary containing 'guide', 'model' and 'svi_result' specifying a trained SVI model
        purge_extra : Optional[bool], optional
            Whether to purge variables containing 'auto', 'base' or 'unwrapped' often used in reparamaterization, by default True
        rkey : Optional[jax.random.PRNGKey], optional
            PRNG key to use, by default jax.random.PRNGKey(5)

        Returns
        -------
        pandas.DataFrame
            ArviZ Summary of results

        Raises
        ------
        AssertionError
            Must supply one of sampler or svi_dict
        """

        if sampler is None and (svi_res_dict is None):
            raise AssertionError("Must svi results dictionary or sampled sampler")

        elif sampler is not None:
            self.sampling_results = az.from_numpyro(sampler)
            self.sampling_results = self.parse(self.sampling_results,purge_extra=purge_extra)
        else:
            assert 'guide' in svi_res_dict.keys()
            assert 'model' in svi_res_dict.keys()
            assert 'svi_result' in svi_res_dict.keys()

            post_raw = svi_res_dict['guide'].sample_posterior(rkey, svi_res_dict['svi_result'].params, sample_shape = ((1000,)))
            #Convert to arviz
            post_dict = {}
            for key in post_raw:
                post_dict[key] = post_raw[key][jnp.newaxis,]
            self.svi_results = az.from_dict(post_dict)
            self.svi_results = self.parse_injested_data(self.svi_results,purge_extra=purge_extra)


        return

    def parse_injested_data(self,data,purge_extra:bool=True):
        var_names = list(data.posterior.to_dataframe().columns)
        
        for var in var_names:
            if 'theta' in var:
                new_theta = np.remainder(data['posterior'][var]+np.pi, np.pi)
                data['posterior'][var] = new_theta

        if purge_extra:
            to_drop = []
            for var in var_names:
                if ('base' in var) or ('auto' in var) or ('unwrapped' in var):
                    to_drop.append(var)

        data.posterior = data.posterior.drop_vars(to_drop)
        return data

    def render_best_fit_mode(self,which='SVI'):
        assert which in ['svi','SVI','sampler']
        if which.upper()=='SVI':
            medians = self.svi_results.posterior.median()
            median_params = jnp.array([medians[name].data for name in self.prior.param_names])
            mod = self.renderer.render_source(median_params, self.prior.profile_type)
        elif which == 'sampler':
            medians = self.sampling_results.posterior.median() 
            median_params = jnp.array([medians[name].data for name in self.prior.param_names])
            mod = self.renderer.render_source(median_params, self.prior.profile_type)
        return mod