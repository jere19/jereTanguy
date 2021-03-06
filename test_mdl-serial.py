#Requieres to be run with IPython to use %prun magic
#Will run on standard python without profiling

import cell_mdl
import numpy
import pylab

#create model objects of the two type
m3=cell_mdl.Red3(30,50)
m6=cell_mdl.Red6(30,50)
#define max simulation time 
tmax=100


def simu_euler_a(mdl,tmax):
    """Computes euler integration of model object 'mdl' until time 'tmax'.
    Uses adaptative time steps."""
    #Integration parameters
    decim=20
    NbIter=0
    dt=0.05
    Ft = 0.15
    dtMin = dt
    dtMax = 6
    dVmax = 1
    #Initialise storage variables
    t=numpy.zeros(round(tmax/(dt*decim))+1)
    Vm=numpy.zeros((mdl.Nx,mdl.Ny,round(tmax/(dt*decim))+1))
    #Integration
    while mdl.time<tmax:
        Ist=0.2/2*(numpy.sign(numpy.sin(2*numpy.pi*mdl.time/(1*tmax)))+1)*numpy.sin(2*numpy.pi*mdl.time/(1*tmax))
        mdl.Istim[5:20,5]=Ist
       # mdl.Istim[50:95,100]=Ist
        mdl.derivT(dt)
        #define new time step
        dt = dtMin*dVmax/numpy.max(abs(mdl.dY[...,0].all())-Ft);
        if dt > dtMax:
            dt = dtMax
        if dt < dtMin:
            dt = dtMin
        mdl.time+=dt
        #stores time and state 
        if not round(mdl.time/dt)%decim:
            NbIter+=1
            t[NbIter]=mdl.time
            Vm[...,NbIter]=mdl.Y[...,0].copy()
    return t,Vm

#Calls of simu_euler_a on both objects
# %prun magic is used for profiling with IPython
%prun simu_euler_a(m3,100)
%prun simu_euler_a(m6,100)

#Uncomment following lines to plot final state of both models
#pylab.figure()
#m3.plotstate()
#pylab.figure()
#m6.plotstate()
#pylab.show()