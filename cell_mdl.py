"""Tissue models classes:
Tissuemodel: Generic base class, not a functionnal model by itself.
Red3: Uses reduced 3 vars uterine cell model (J.Laforet).
Red6: Uses reduced 6 vars uterine cell model (S.Rihana)."""

import numpy
from scipy.ndimage.filters import correlate1d
try:
    from IPython.parallel import Client
except ImportError:
    HASMPI = False
else:
    HASMPI = True
from warnings import warn
try:
    from enthought.mayavi import mlab
except ImportError:
    HASMAYAVI = False
else:
    HASMAYAVI = True
from scipy.signal import correlate
import locale
locale.setlocale(locale.LC_NUMERIC, 'C')
try:
    import pylab
    import matplotlib.cm as cm
except ImportError:
    HASMATPLOT = False
else:
    HASMATPLOT = True
import multiprocessing as mp
import shmarray
#from math import ceil, log

class TissueModel(object):
    """Generic cell and tissue model."""
    def __init__(self, dim, Nx, Ny=0, Nz=0, noise=0.0, 
                borders=[True,True,True,True,True,True], cylindrical=False):
        """Model init.
            dim: number of variables of state vector.
            Nx: number of cells along X.
            Ny: number of cells along Y.
            Nz: number of cells along Z.
            noise: noise coefficient for initial state.
            borders: boolean array [firstX,lastX,firstY,lastY,firstZ,lastZ]"""   
        #dimensions
        self.Name = "Generic!"
        self.Padding = 4
        self.time = 0
        self.cyl = cylindrical
        if self.cyl:
            borders[2:5] = [False,False]
        #Initialise state given the type of model
        self.dim = dim
        if self.dim == 3:
            Y0 = [-50,0.079257,0.001]
        elif self.dim == 6:
            Y0 = [-50,0.0015709,0.8,0.8,0.079257,0.001]
        else:
            Y0 = numpy.zeros(self.dim)
        #parameters
        self._Cm = 1
        self._Rax = 4500
        self._Ray = 4500
        self._Raz = 4500
        self._hx = 0.03
        self._hy = 0.03
        self._hz = 0.03
        self.flag = True
        #state
        if Nx*Ny*Nz: #3D
            #update dims with padding
            self.Nx = Nx+borders[0]*self.Padding/2+borders[1]*self.Padding/2
            self.Ny = Ny+borders[2]*self.Padding/2+borders[3]*self.Padding/2
            self.Nz = Nz+borders[4]*self.Padding/2+borders[5]*self.Padding/2
            #generate full state
            self.Y = numpy.tile(numpy.array(Y0),(self.Nx,self.Ny,self.Nz,1))
            #mask for padding borders  
            self.mask = 1e-4*numpy.ones(self.Y.shape[0:-1])
            self.mask[borders[0]*self.Padding/2:
                self.Nx-borders[1]*self.Padding/2,borders[2]*self.Padding/2:
                self.Ny-borders[3]*self.Padding/2,borders[4]*self.Padding/2:
                self.Nz-borders[5]*self.Padding/2] = numpy.ones(
                (self.Nx-borders[0]*self.Padding/2-borders[1]*self.Padding/2,
                self.Ny-borders[2]*self.Padding/2-borders[3]*self.Padding/2,
                self.Nz-borders[4]*self.Padding/2-borders[5]*self.Padding/2)
                )
            #diffusion coeffs
            self.Dx = 1/(self._Rax*self._Cm*self._hx**2)
            self.Dy = 1/(self._Ray*self._Cm*self._hy**2)
            self.Dz = 1/(self._Raz*self._Cm*self._hz**2)
            self.parlist.extend(['Dx', 'Dy', 'Dz'])
            self.derivS = self._derivS3
            self.stimCoord = [0,0,0,0,0,0]
            self.stimCoord2 = [0,0,0,0,0,0]
        elif Nx*Ny: #2D
            self.Nx = Nx+borders[0]*self.Padding/2+borders[1]*self.Padding/2
            self.Ny = Ny+borders[2]*self.Padding/2+borders[3]*self.Padding/2
            self.Y = numpy.tile(numpy.array(Y0),(self.Nx,self.Ny,1))
            #mask for padding borders    
            self.mask = 1e-4*numpy.ones(self.Y.shape[0:-1])
            self.mask[borders[0]*self.Padding/2:
                self.Nx-borders[1]*self.Padding/2,borders[2]*self.Padding/2:
                self.Ny-borders[3]*self.Padding/2] = numpy.ones(
                (self.Nx-borders[0]*self.Padding/2-borders[1]*self.Padding/2,
                self.Ny-borders[2]*self.Padding/2-borders[3]*self.Padding/2)
                )
            #diffusion coeffs
            self.Dx = 1/(self._Rax*self._Cm*self._hx**2)
            self.Dy = 1/(self._Ray*self._Cm*self._hy**2)
            self.parlist.extend(['Dx','Dy'])
            self.derivS = self._derivS2
            self.stimCoord = [0,0,0,0]
            self.stimCoord2 = [0,0,0,0]
        elif Nx>1: #1D
            self.Nx = Nx+borders[0]*self.Padding/2+borders[1]*self.Padding/2
            self.Y = numpy.tile(numpy.array(Y0),(self.Nx,1))
            #mask for padding borders    
            self.mask = 1e-4*numpy.ones(self.Y.shape[0:-1])
            self.mask[borders[0]*self.Padding/2:self.Nx-borders[1]*
                self.Padding/2] = numpy.ones(
                (self.Nx-borders[0]*self.Padding/2-borders[1]*self.Padding/2)
                )  
            #diffusion coeffs
            self.Dx = 1/(self._Rax*self._Cm*self._hx**2)
            self.parlist.append('Dx')
            self.derivS = self._derivS1   
            self.stimCoord = [0,0]
            self.stimCoord2 = [0,0]                        
        else: #0D
            self.Y = numpy.array(Y0)
            self.derivS = self._derivS0
            self.stimCoord = [0,0]
            self.stimCoord2 = [0,0]
        self.R = 8.314
        self.T = 295
        self.F = 96.487
        self.Ca0 = 3*numpy.ones(self.Y.shape[0:-1])
        self.Istim = numpy.zeros(self.Y.shape[0:-1])
        self.masktempo = 1 
        self.parlist.extend(['R','T','F','_Cm','_Rax','_Ray','_Raz','_hx','_hy',
                                                       '_hz','masktempo','cyl'])
        #option for noisy initial state
        if noise != 0.0:
            self.Y *= 1+(numpy.random.random(self.Y.shape)-.5)*noise 

    def reset(self):
        """set Y and time parameters to original value"""
        self.time = 0
        if self.dim == 3:
            Y0 = [-50,0.079257,0.001]
        elif self.dim == 6:
            Y0 = [-50,0.0015709,0.8,0.8,0.079257,0.001]
        else:
            Y0 = numpy.zeros(self.dim)
        shp = list(self.Y.shape)
        shp[-1] = 1
        self.Y = numpy.tile(numpy.array(Y0),shp)

    def copyparams(self,mdl):
        """Retrieves parameters from 'mdl', if it has the same class as self."""
        if self.Name!=mdl.Name:
            print "Can't copy from different model type."
        else:
            for par in mdl.parlist:
                self.__dict__[par]=mdl.__dict__[par]

    def _get_hx(self):
        """accessor of hx"""
        return self._hx
    def _set_hx(self,hx):
        """mutator of hx"""
        self._hx = hx
        try: self.Dx=1/(self._Rax*self._Cm*self._hx**2)
        except ValueError: warn("ValueError! Dx was not changed")
    hx = property(_get_hx,_set_hx)

    def _get_hy(self):
        """accessor of hy"""
        return self._hy
    def _set_hy(self,hy):
        """mutator of hy"""
        self._hy = hy
        try: self.Dy=1/(self._Ray*self._Cm*self._hy**2)
        except ValueError: warn("ValueError! Dy was not changed")
    hy = property(fget=_get_hy,fset=_set_hy)

    def _get_hz(self):
        """accessor of hz"""
        return self._hz
    def _set_hz(self,hz):
        """mutator of hz"""
        self._hz = hz
        try: self.Dz=1/(self._Raz*self._Cm*self._hz**2)
        except ValueError: warn("ValueError! Dz was not changed")
    hz = property(fget=_get_hz,fset=_set_hz)

    def _get_Cm(self):
        """accessor of Cm"""
        return self._Cm
    def _set_Cm(self,Cm):
        """mutator of Cm"""
        self._Cm= Cm 
        try: self.Dx=1/(self._Rax*self._Cm*self._hx**2)
        except ValueError: warn("ValueError! Dx was not changed")
        try: self.Dy=1/(self._Ray*self._Cm*self._hy**2)
        except ValueError: warn("ValueError! Dy was not changed")
        try: self.Dz=1/(self._Raz*self._Cm*self._hz**2)
        except ValueError: warn("ValueError! Dz was not changed")
    Cm = property(fget=_get_Cm,fset=_set_Cm)

    def _get_Rax(self):
        """accessor of Rax"""
        return self._Rax
    def _set_Rax(self,Rax):
        """mutator of Rax"""
        self._Rax = Rax
        try: self.Dx=1/(self._Rax*self._Cm*self._hx**2)
        except ValueError: warn("ValueError! Dx was not changed")
    Rax = property(fget=_get_Rax,fset=_set_Rax)

    def _get_Ray(self):
        """accessor of Ray"""
        return self._Ray
    def _set_Ray(self,Ray):
        """mutator of Ray"""
        self._Ray = Ray
        try: self.Dy=1/(self._Ray*self._Cm*self._hy**2)
        except ValueError: warn("ValueError! Dy was not changed")
    Ray = property(fget=_get_Ray,fset=_set_Ray)

    def _get_Raz(self):
        """accessor of Raz"""
        return self._Raz
    def _set_Raz(self,Raz):
        """mutator of Raz"""
        self._Raz = Raz
        try: self.Dz=1/(self._Raz*self._Cm*self._hz**2)
        except ValueError: warn("ValueError! Dz was not changed")
    Raz = property(fget=_get_Raz,fset=_set_Raz)


    def getlistparams(self):
        """gives the list of parameters of object self"""
        dictparam = {}
        for par in self.parlist:
            dictparam[par]=self.__dict__[par]
        return dictparam

    def setlistparams(self,dictparam):
        """Retrieves parameters from dictparam"""
        for par in dictparam:
            self.__dict__[par]=dictparam[par]

    def savedict(self):
        d = self.__dict__.copy()
        d['derivS'] = self.derivS.__repr__()
        return d

    
    def __repr__(self):
        """Print model infos."""
        return "Model "+ self.Name +", dimensions: "+str(self.Y.shape)+" ."    

    def _derivative2(self,inumpyut,axis,output=None, mode="wrap",cval=0.0):
        """Computes spatial derivative to get propagation."""
        return correlate1d(inumpyut, [1, -2, 1], axis, output, mode, cval, 0)
    def diff1d(self,Var):
        """Computes spatial derivative to get propagation."""
        Dif=self.Dx*self._derivative2(Var,0)
        if self.flag:
            Dif[self.stimCoord[0]:self.stimCoord[1]]=0
            Dif[self.stimCoord2[0]:self.stimCoord2[1]]=0
        return Dif*self.mask   
    def diff2d(self,Var):
        """Computes spatial derivative to get propagation."""
        Dif=self.Dx*self._derivative2(Var,0) + self.Dy*self._derivative2(Var,1)
            
        if self.flag:
            Dif[self.stimCoord[0]:self.stimCoord[1],self.stimCoord[2]:
                                                            self.stimCoord[3]]=0
            Dif[self.stimCoord2[0]:self.stimCoord2[1],self.stimCoord2[2]:
                                                           self.stimCoord2[3]]=0
        return Dif*self.mask
    def diff3d(self,Var):
        """Computes spatial derivative to get propagation."""
        derivx = self.Dx * self._derivative2(Var,0)
        derivy = self.Dy * self._derivative2(Var,1)
        derivz = self.Dz * self._derivative2(Var,2)
        Dif = derivx + derivy + derivz
        if self.flag:
            Dif[self.stimCoord[0]:self.stimCoord[1],self.stimCoord[2]:
                        self.stimCoord[3],self.stimCoord[4]:self.stimCoord[5]]=0
            Dif[self.stimCoord2[0]:self.stimCoord2[1],self.stimCoord2[2]:
                    self.stimCoord2[3],self.stimCoord2[4]:self.stimCoord2[5]]=0
        return Dif*self.mask    
    def _derivS0(self):
        """Computes spatial derivative to get propagation. (0D)"""
        pass
    def _derivS1(self):
        """Computes spatial derivative to get propagation. (1D)"""
        self.dY[...,0]+=self.diff1d(self.Y[...,0])
    def _derivS2(self):
        """Computes spatial derivative to get propagation. (2D)"""
        self.dY[...,0]+=self.diff2d(self.Y[...,0])
    def _derivS3(self):
        """Computes spatial derivative to get propagation. (3D)"""
        self.dY[...,0]+=self.diff3d(self.Y[...,0])    
    def plotstate(self):
        """Plot state of the model with the suitable method, according its 
            dimensions."""
        if self.Y.ndim==1:
            print "State: Vm={0} mV, nK={1} and [Ca]={2} mmol.".format(
                                                self.Y[0],self.Y[1],self.Y[2])
        elif self.Y.ndim==2:
            #pylab.figure()
            pylab.plot(self.Y)
            pylab.legend( ('Vm','nK','[Ca]'))
            #pylab.show()
        elif self.Y.ndim==3:
            #pylab.figure()
            pylab.subplot(212)
            pylab.imshow(self.Y[...,0])
            pylab.colorbar()
            pylab.title('Vm')
            pylab.subplot(221)
            pylab.imshow(self.Y[...,1])
            pylab.colorbar()
            pylab.title('nK')
            pylab.subplot(222)
            pylab.imshow(self.Y[...,2])
            pylab.colorbar()
            pylab.title('[Ca]')
            #pylab.show()
        elif self.Y.ndim==4:
            print "Display of 2.5D models currrently unsupported."
        else:
            print "Uncompatible model dimensions for plotting."

class Red3(TissueModel):
    """Cellular and tissular model Red3"""
    def __init__(self,Nx,Ny=0,Nz=0,noise=0.0,
                     borders=[True,True,True,True,True,True],cylindrical=False):
        """Model init."""
        self.parlist=['Gk','Gkca','Gl','Kd','fc','alpha','Kca','El','Ek','Gca2',
                                                    'vca2','Rca','Jbase','Name']
        #Generic elements
        TissueModel.__init__(self,3,Nx,Ny,Nz,noise,borders,cylindrical)
        #Default Parameters
        self.Name="Red3"
        self.Gk=0.064
        self.Gkca=0.08
        self.Gl=0.0055
        self.Kd=0.01
        self.fc=0.4
        self.alpha=4*10**-5
        self.Kca=0.01
        self.El=-20
        self.Ek=-83
        self.Gca2=-0.02694061
        self.vca2=-20.07451779
        self.Rca=5.97139101
        self.Jbase=0.02397327
        self.dY=numpy.empty(self.Y.shape)
        #self.Istim[5:20,5]=0.2
        

    def derivT(self,dt,MP=False):
        """Computes temporal derivative for red3 model."""
        #Variables
        Vm=self.Y[...,0]
        nk=self.Y[...,1]
        Ca=self.Y[...,2]  
        #Nerst
        Eca=((self.R*self.T)/(2*self.F))*numpy.log(self.Ca0/Ca)
        #H inf x
        hki=1/(1+numpy.exp((4.2-Vm)/21.1))
        #Tau x
        tnk=23.75*numpy.exp(-Vm/72.15)
        #Courants
        Ica2=self.Jbase-self.Gca2*(Vm-Eca)/                                    \
            (1+numpy.exp(-(Vm-self.vca2)/self.Rca))
        Ik=self.Gk*nk*(Vm-self.Ek)
        Ikca=self.Gkca*Ca**2/(Ca**2+self.Kd**2)*(Vm-self.Ek)
        Il=self.Gl*(Vm-self.El)        
        #Derivees
        self.dY[...,0] = (self.Istim - Ica2 -Ik - Ikca -Il)/self.Cm
        self.dY[...,1] = (hki-nk)/tnk
        self.dY[...,2] = self.fc*(-self.alpha*Ica2 - self.Kca*Ca)
        self.dY *= self.masktempo
        #update Y
        self.derivS()
        # if the integrator uses shared memory, we don't allocate Y here
        if not(MP):    
            self.Y+=self.dY*dt

class Red6(TissueModel):
    """Cellular and tissular model Red6"""
    def __init__(self,Nx,Ny=0,Nz=0,noise=0.0,
                borders=[True,True,True,True,True,True],cylindrical=False):
        """Model init."""
        self.parlist=['Gca','Gk','Gkca','Gl','Kd','fc','alpha','Kca','El','Ek',
                                                                        'Name']
        #Generic elements
        TissueModel.__init__(self,6,Nx,Ny,Nz,noise,borders,cylindrical)
        #Default Parameters
        self.Name="Red6"
        self.Gca=0.09
        self.Gk=0.064
        self.Gkca=0.08
        self.Gl=0.0055
        self.Kd=0.01
        self.fc=0.4
        self.alpha=4*10**-5
        self.Kca=0.01
        self.El=-20
        self.Ek=-83
        self.dY=numpy.empty(self.Y.shape)
        #self.Istim[5:20,5]=0.2
        

    def derivT(self,dt,MP=False):
        """Computes temporal derivative for red3 model."""
        #Variables
        Vm=self.Y[...,0]
        mca=self.Y[...,1]
        h1ca=self.Y[...,2]
        h2ca=self.Y[...,3]
        nk=self.Y[...,4]
        Ca=self.Y[...,5]
        #Nerst
        Eca=((self.R*self.T)/(2*self.F))*numpy.log(self.Ca0/Ca)

        
        #H inf x
        mcai=1/(1+numpy.exp((-27-Vm)/6.6))
        hcai=1/(1+numpy.exp((Vm+34)/5.4))
        hki=1/(1+numpy.exp((4.2-Vm)/21.1))

        #Tau x
        tmca=0.64*numpy.exp(-0.04*Vm)+1.188
        th1ca=160*numpy.ones(Vm.shape)
        Imodif=numpy.nonzero((Vm<-10)|(Vm>45))
        th1ca[Imodif]=24.65*numpy.exp(-0.07281*Vm[Imodif])+                    \
                                            17.64*numpy.exp(0.029*Vm[Imodif])
        th2ca=160
        tnk=23.75*numpy.exp(-Vm/72.15)
       
        #Alias
        fca=1/(1+Ca)
        hca=0.38*h1ca+0.22*h2ca+0.06

        #Courants
        Ica=self.Gca*mca*mca*hca*fca*(Vm-Eca)
        Ik=self.Gk*nk*(Vm-self.Ek)
        Ikca=self.Gkca*Ca**2/(Ca**2+self.Kd**2)*(Vm-self.Ek)
        Il=self.Gl*(Vm-self.El)
            
        #Derivees
        self.dY[...,0] = (self.Istim - Ica -Ik - Ikca -Il)/self.Cm
        self.dY[...,1] = (mcai-mca)/tmca
        self.dY[...,2] = (hcai-h1ca)/th1ca
        self.dY[...,3] = (hcai-h2ca)/th2ca
        self.dY[...,4] = (hki-nk)/tnk
        self.dY[...,5] = self.fc*(-self.alpha*Ica - self.Kca*Ca)
        #update Y
        self.dY *= self.masktempo
        self.derivS()
        if not(MP):
            self.Y+=self.dY*dt

def profilepara(*args):
    """Function calling the engine process function and profiling it"""
    from cProfile import runctx
    rank = args[0]
    runctx("parallelcompMP(*args)", globals(), locals(), 
                                        filename=('Process-'+str(rank)+'.prof'))

def parallelcompMP(rank,tmax,Nx,Ny,Nz,N,stimCoord,stimCoord2,listparam,Iamp,
                                    dt,Y,mask,count,Vm,time,mutex,att):
    """Function used by the engine processes"""

    try:
        from progressbar import Bar,ProgressBar,Percentage
        showbar=True
    except ImportError:
        showbar=False

#    def findlimitsx(rank,nbx,Nx):
#        from numpy import trunc
#        newNxx = trunc( float(Nx) / nbx )
#        x = [0,0]
#        if rank%nbx==(nbx-1):
#            x = [rank%nbx * (newNxx+2) - rank%nbx * 2,Nx]
#        elif (rank%nbx==0):
#            x = [0,newNxx+2]
#        else:
#            x[0] = rank%nbx * (newNxx+2) - rank%nbx * 2
#            x[1] = x[0] + newNxx + 2
#        return x,x[1] - x[0]

    def findlimitsx(rank,nbx,Nx):
        from numpy import arange,array_split
        tmp = arange(Nx+2*nbx-2+1)
        tab = array_split(tmp,nbx)
        l = len(tab[rank])
        x = [ tab[rank][0] - rank*2 - int(rank != 0), tab[rank][-1] - rank*2]
        return x,x[1]-x[0]
        
#     Which rows should I compute?
    [x,newNx] = findlimitsx(rank,N,Nx)

#     Stimulation (global coordinates)
    xyIstim1 = stimCoord 
    xyIstim2 = stimCoord2

#     computing the local coordinates
    if (xyIstim1[0] > x[-1]) or (xyIstim1[1] < x[0]):
        xyIstim1[0:2] = [-1,-1]
    else:
        xyIstim1[0:2] = [max(xyIstim1[0],x[0])-x[0],
                           min(xyIstim1[1],x[-1])-x[0]]

    if (xyIstim2[0] > x[-1]) or (xyIstim2[1] < x[0]):
        xyIstim2[0:2] = [-1,-1]
    else:
        xyIstim2[0:2] = [max(xyIstim2[0],x[0])-x[0],
                           min(xyIstim2[1],x[-1])-x[0]]

#     Creation of the model (one for each process)
    bdrs=[False] * (2 + bool(Ny)*2 + bool(Nz)*2)
    if listparam['Name'] == 'Red6':
        mdl = Red6(Nx=newNx,Ny=Ny,Nz=Nz,borders=bdrs)
    elif listparam['Name'] == 'Red3':
        mdl = Red3(Nx=newNx,Ny=Ny,Nz=Nz,borders=bdrs)
    mdl.setlistparams(listparam)
    mdl.Name += 'p'

    mdl.Y = Y[x[0]:x[1],...]
    mdl.mask = mask[x[0]:x[1],...]

    if rank == 0:
        mdl.mask[-1,...] = 0
    if rank == N - 1:
        mdl.mask[0,...] = 0
#    else:
#        mdl.masktempo[-2:,...] = 0
#    
#    mdl.masktempo = numpy.ones(mdl.dY.shape[:-1]) + mdl.masktempo
    

    def modify(var,x):
        if not(isinstance(var,int)) and not(isinstance(var,float)):
            return var[x[0]:x[1],...]
        else:
            return var

    mdl.masktempo = modify(mdl.masktempo,x)
    mdl.hx = modify(mdl.hx,x)
    mdl.hy = modify(mdl.hy,x)
    mdl.hz = modify(mdl.hz,x)
    mdl.Rax = modify(mdl.Rax,x)
    mdl.Ray = modify(mdl.Ray,x)
    mdl.Raz = modify(mdl.Raz,x)

#     Tells the model where the stimuli are
    if xyIstim1[0] != -1:
        mdl.stimCoord = xyIstim1
    if xyIstim2[0] != -1:
        mdl.stimCoord2 = xyIstim2

    def _stim1(mdl,stimCoord,Ist):
        if stimCoord[0] != -1:
            mdl.Istim[stimCoord[0]:stimCoord[1]]=Ist

    def _stim2(mdl,stimCoord,Ist):
        if stimCoord[0] != -1 and stimCoord[2] != -1:
            mdl.Istim[stimCoord[0]:stimCoord[1],stimCoord[2]:stimCoord[3]]=Ist

    def _stim3(mdl,stimCoord,Ist):
        if stimCoord[0] != -1 and stimCoord[2] != -1:
            mdl.Istim[stimCoord[0]:stimCoord[1],stimCoord[2]:stimCoord[3],
                                       stimCoord[4]:stimCoord[5]]=Ist

    decim=20
    NbIter=0
#    Ft = 0.15

    if Nx*Ny*Nz:
        stim = _stim3
    elif Nx*Ny:
        stim = _stim2
    elif Nx:
        stim = _stim1
    
    test = [rank != 0,rank != N-1]
    if (rank==0) and showbar:
        pbar = ProgressBar(widgets=[Percentage(), Bar()],
                            maxval=len(time)).start()

    lx = mdl.dY.shape[0]

    mdl.flag = True

    while (mdl.time<tmax):
        Ist=Iamp/2*(numpy.sign(numpy.sin(2*numpy.pi*mdl.time/(2*tmax)))+1)*   \
                   numpy.sin(2*numpy.pi*mdl.time/(2*tmax))

        if mdl.flag and (mdl.time != 0) and (Ist == 0):
            mdl.flag = False

        stim(mdl,xyIstim1,Ist)
        stim(mdl,xyIstim2,Ist)

        mdl.derivT(dt,True)

        if (not round(mdl.time/dt)%decim):
            if not mutex.acquire(timeout=2):
                print('timeout mutex')
            count.value += 1
            if count.value == N:
                for i in range(N-1):
                    att.release()
                count.value = 0
                mutex.release()
            else:
                mutex.release()
                if not att.acquire(timeout=2):
                    print('timeout att')

        Y[x[0]+test[0]:x[1]-test[1],...] += mdl.dY[0+test[0]:lx-test[1],...]*dt

        mdl.time +=dt
        
        if (rank == 0) and (not round(mdl.time/dt)%decim):
            NbIter+=1
            time[NbIter]=mdl.time
            Vm[...,NbIter] = Y[...,0]           
            if showbar:
                pbar.update(mdl.time)

    if (rank == 0) and showbar:    
        pbar.finish()



class IntGen():
    """Generic integrator class"""

    def __init__(self,mdl):
        """The constructor.
                mdl : model (of class Red3 or Red6)
        """
        self.mdl = mdl
        self.Iamp=0.2
        
    def savemodel(self,filename):
        d = self.__dict__.copy()
        d['mdl'] = self.mdl.__repr__()
        try:
            d['t'] = numpy.array(d['t'])
            d['Y'] = numpy.array(d['Y'])
            d['Vm'] = numpy.array(d['Vm'])
        except KeyError:
            pass
        mdl = self.mdl.savedict()
        numpy.savez(filename,tmdl=d,mdl=mdl)
        print 'Model saved in ' + filename

    def save(self,filename,limitsize=500,tmax=1000):
        """save t and Vm using the method numpy.savez"""
        count = 1
#        nmax = round(tmax * self.dt)
        t_tmp = self.t
        v_tmp = self.Vm

        if v_tmp.nbytes / (2**20) > limitsize:
            toobig = True
            while toobig:
                while t_tmp[-1] > tmax*count:
                    ind = t_tmp.searchsorted(tmax*count)
                    if v_tmp[...,:ind].nbytes / (2**20) > limitsize:
                        break
                    else:
                        toobig = False
                    logY=open(filename+'-'+str(count)+'-t.npy','w')
                    numpy.save(logY,t_tmp[:ind])
                    logY=open(filename+'-'+str(count)+'-Y.npy','w')
                    numpy.save(logY,v_tmp[...,:ind])
                    logY.close()
                    t_tmp = t_tmp[ind:]
                    v_tmp = v_tmp[...,ind:]
                    count += 1
                if len(t_tmp) > 0:
                    if v_tmp.nbytes / (2**20) > limitsize:
                        break
                    else:
                        toobig = False
                        logY=open(filename+'-'+str(count)+'-t.npy','w')
                        numpy.save(logY,t_tmp)
                        logY=open(filename+'-'+str(count)+'-Y.npy','w')
                        numpy.save(logY,v_tmp)
                        logY.close()
                if toobig:
                    warn('the file is too big: tmax is divided by 2')
                    tmax /= 2
        else:
            logY = open(filename+'-t.npy','w')
            numpy.save(logY,t_tmp)
            logY = open(filename+'-Y.npy','w')
            numpy.save(logY,v_tmp)
            logY.close()



        f = open(filename+'.txt','w')
        f.write('Integrator : ' + self.__class__.__name__ +' \n')
        if not('Nz' in self.mdl.__dict__):
            if not ('Ny' in self.mdl.__dict__):
                f.write('Dimension : ' + str(self.mdl.Nx) + ' (1D) \n')
            else:
                f.write('Dimension : ' + str(self.mdl.Nx) + 'x' + 
                                                str(self.mdl.Ny) + ' (2D) \n')
        else:
            f.write('Dimension : ' + str(self.mdl.Nx) + 'x' + str(self.mdl.Ny) +
                                            str(self.mdl.Ny)  + ' (2.5D) \n')
        f.write('Duration : ' + str(max(self.t)) + 'ms \n')
        f.write('Coordinates of the stimulation :' + str(self.mdl.stimCoord) +
                                     ' and ' + str(self.mdl.stimCoord2) +' \n')
        f.write('Model : ' + self.mdl.Name +'\n')
        f.write('\t parameters of this models : \n')
        for par in self.mdl.parlist:
            f.write('\t\t ' + str(par) + ' : ' + str(self.mdl.__dict__[par]) + 
                                                                        '\n')
        f.close()


    def reset(self):
        """set Y and time parameters of the model to their original value"""
        self.mdl.reset()



    def show(self):
        """show Vm in a graph. Works for 1D projects only"""
        assert 'Vm' in self.__dict__,"""We could not find the attribute Vm. 
                            Have you tried running "compute" method before?"""

        if self.Vm.ndim == 2:
            assert HASMATPLOT, "Sorry, you have to have pylab installed!"
            pylab.imshow(self.Vm,aspect='auto',cmap=cm.jet)
            pylab.show()
        elif self.Vm.ndim == 3:
            assert HASMAYAVI, "Sorry, you have to have mayavi installed!"
            s = mlab.surf(self.Vm[...,1])
            raw_input("Press Enter to lauch the simulation...")
            for i in range(1,self.Vm.shape[-1]):
                s.mlab_source.scalars = self.Vm[...,i]
        elif self.Vm.ndim == 4:
            assert HASMAYAVI, "Sorry, you have to have mayavi installed!"
            p = mlab.pipeline.scalar_field(self.Vm[...,1])
            s = mlab.pipeline.image_plane_widget( p,
                                        plane_orientation='x_axes',
                                        slice_index=self.mdl.stimCoord[0],
                                        vmin = self.Vm[...,1:].min(),
                                        vmax = self.Vm[...,1:].max()
                                    )

            s2 = mlab.pipeline.image_plane_widget(p,
                                        plane_orientation='y_axes',
                                        slice_index=self.mdl.stimCoord[2],
                                        vmin = self.Vm[...,1:].min(),
                                        vmax = self.Vm[...,1:].max()
                                    )
            s3 = mlab.pipeline.image_plane_widget( p,
                                        plane_orientation='z_axes',
                                        slice_index=self.mdl.stimCoord[4],
                                        vmin = self.Vm[...,1:].min(),
                                        vmax = self.Vm[...,1:].max()
                                    )
            mlab.scalarbar(s,orientation='vertical',nb_labels=4,
                                                            label_fmt='%.3f')
            mlab.outline(color=(1,1,1))
            raw_input("Press Enter to lauch the simulation...")
            for i in range(1,self.Vm.shape[-1]):
                p.mlab_source.scalars = self.Vm[...,i]

    def speed(self,coord1,coord2,fshow=False):
        """calculate the mean spead between two points"""
        assert 'Vm' in self.__dict__,"""We could not find the attribute Vm. 
                            Have you tried running "compute" method before?"""

        if isinstance(coord1,list):
            coord1 = tuple(coord1)
        if isinstance(coord2,list):
            coord2 = tuple(coord2)

        x = self.Vm[coord1]
        y = self.Vm[coord2]

        CrossCorrelation = correlate(x-x.mean(),y-y.mean(),mode='same')

        i_delay = numpy.argmax(CrossCorrelation)

        vectdelay = numpy.linspace(-self.t[-1]/2,self.t[-1]/2,
                                                        len(CrossCorrelation))


        delay = abs(vectdelay[i_delay]) * self.dt

        if self.mdl.Y.ndim == 2:
            dist = abs(coord2 - coord1) * self.mdl.hx
        elif self.mdl.Y.ndim == 3:
            dist = numpy.sqrt( (abs(coord2[0] - coord1[0]) * self.mdl.hx)**2 + \
                                (abs(coord2[1] - coord1[1]) * self.mdl.hy)**2 )
        elif self.mdl.Y.ndim == 4:
            dist = numpy.sqrt( (abs(coord2[0] - coord1[0]) * self.mdl.hx)**2 + \
            (abs(coord2[1] - coord1[1]) * self.mdl.hy)**2 + (abs(coord2[0] - \
            coord1[0])  * self.mdl.hz)**2 )

        if fshow:
            pylab.subplot(211)
            pylab.plot(self.t,x)
            pylab.plot(self.t,y)
            pylab.subplot(212)
            pylab.plot(vectdelay,CrossCorrelation)
            pylab.show()
            

        return dist / delay, CrossCorrelation

class IntSerial(IntGen):
    """Integrator class using serial computation"""

    def __init__(self,mdl):
        """The constructor.
                mdl : model (of class Red3 or Red6)
        """
        IntGen.__init__(self,mdl)

    def _stim0(self,stimCoord,Ist):
        self.mdl.Istim = Ist
    
    def _stim1(self,stimCoord,Ist):
        self.mdl.Istim[stimCoord[0]:stimCoord[1]]=Ist

    def _stim2(self,stimCoord,Ist):
        self.mdl.Istim[stimCoord[0]:stimCoord[1],stimCoord[2]:stimCoord[3]]=Ist

    def _stim3(self,stimCoord,Ist):
        self.mdl.Istim[stimCoord[0]:stimCoord[1],stimCoord[2]:stimCoord[3],
                                                stimCoord[4]:stimCoord[5]]=Ist

    def compute(self,tmax=500,stimCoord=-1,stimCoord2=-1):        
        """Compute.
                tmax : maximum duration (in ms)
                stimCoord,stimCoord2 : Coordinates of the stimulations
        """
        self.decim=10
        NbIter=0
        self.dt=0.05
        Ft = 0.15
        dtMin = self.dt
        dtMax = 6
        dVmax = 1

        time = self.mdl.time

#        self.t=numpy.ones(round(tmax/(self.dt*self.decim))+1) * self.mdl.time
        self.t=shmarray.ones(round(tmax/(self.dt*self.decim))+1) * time
        
        if stimCoord == -1:
            stimCoord = self.mdl.stimCoord
        else:
            self.mdl.stimCoord = stimCoord

        if stimCoord2 == -1:
            stimCoord2 = self.mdl.stimCoord2
        else:
            self.mdl.stimCoord2 = stimCoord2

#        flag0D = False
#        if self.mdl.Y.ndim == 1:
#            self.Vm = numpy.empty(len(self.t))
#            self.stim = self._stim0
#            flag0D = True
#        elif self.mdl.Y.ndim == 2:
#            self.Vm = numpy.empty((self.mdl.Nx,len(self.t)))
#            self.stim = self._stim1
#        elif self.mdl.Y.ndim == 3:
#            self.Vm = numpy.empty((self.mdl.Nx,self.mdl.Ny,len(self.t)))
#            self.stim = self._stim2
#        elif self.mdl.Y.ndim == 4:
#            self.Vm = numpy.empty((self.mdl.Nx,self.mdl.Ny,self.mdl.Nz,
#                                                                len(self.t)))

        flag0D = False
        if self.mdl.Y.ndim == 1:
            self.Vm = shmarray.zeros(len(self.t))
            self.stim = self._stim0
            flag0D = True
        elif self.mdl.Y.ndim == 2:
            self.Vm = shmarray.zeros((self.mdl.Nx,len(self.t)))
            self.stim = self._stim1
        elif self.mdl.Y.ndim == 3:
            self.Vm = shmarray.zeros((self.mdl.Nx,self.mdl.Ny,len(self.t)))
            self.stim = self._stim2
        elif self.mdl.Y.ndim == 4:
            self.Vm = shmarray.zeros((self.mdl.Nx,self.mdl.Ny,self.mdl.Nz,
                                                                len(self.t)))

            self.stim = self._stim3

        assert flag0D or ( self.mdl.Y.ndim - 1 == len(stimCoord)/2 and \
                self.mdl.Y.ndim - 1 == len(stimCoord2)/2 ),         \
                "stimCoord and/or stimCoord2 have incorrect dimensions"

        self.mdl.flag = True


        Iamp = self.Iamp
        #Integration
        while time<tmax:
            Ist = Iamp/2*(numpy.sign(numpy.sin(
            2*numpy.pi*time/(2*tmax)
            ) )+1)*numpy.sin(2*numpy.pi*time/(2*tmax))


            if (time != 0) and (Ist == 0):
                self.mdl.flag = False

            self.stim(stimCoord,Ist)
            self.stim(stimCoord2,Ist)
           # mdl.Istim[50:95,100]=Ist
            self.mdl.derivT(self.dt)
            #define new time step
#            self.dt = dtMin*dVmax/numpy.max(abs(self.mdl.dY[...,0].all())-Ft)
#            if self.dt > dtMax:
#                self.dt = dtMax
#            if self.dt < dtMin:
#                self.dt = dtMin
            time+=self.dt
            #stores time and state 
            if not round(time/self.dt)%self.decim:
                NbIter+=1
                self.t[NbIter]=time
                self.Vm[...,NbIter]=self.mdl.Y[...,0].copy()
        self.Vm = self.Vm[...,1:NbIter-1]
        self.t = self.t[...,1:NbIter-1]

class IntParaMP(IntGen):
    """Integrator class using parallel computation"""

    def __init__(self,mdl,N=None):
        """The constructor.
                mdl : model (of class Red3 or Red6)
                N : number of processes
        """
        IntGen.__init__(self,mdl)
        
        self.mdl = mdl
        
        self.Y = shmarray.ones(mdl.Y.shape, numpy.float)
        self.Y[...] = mdl.Y

        if N is None:
            self.N = mp.cpu_count()
        else:
            if N > mp.cpu_count():
                self.N = mp.cpu_count()
                warn("The number of workers asked is higher than the number of available CPUs, I will only launch " + str(self.N) + 'workers')
            else:
                self.N = N
        # data,N = rearrange(_data,N)

        
        
    def compute(self,tmax=500,stimCoord=-1,stimCoord2=-1,profiling=False):
        
        try: Nz = self.mdl.Nz 
        except AttributeError: Nz = 0

        try: Ny = self.mdl.Ny 
        except AttributeError: Ny = 0

        Nx = self.mdl.Nx
    
        if stimCoord == -1:
            stimCoord = self.mdl.stimCoord

        else:
            self.mdl.stimCoord = stimCoord

        if stimCoord2 == -1:
            stimCoord2 = self.mdl.stimCoord2
        else:
            self.mdl.stimCoord2 = stimCoord2

        assert (self.mdl.Y.ndim - 1 == len(stimCoord)/2) and \
                (self.mdl.Y.ndim - 1 == len(stimCoord2)/2), \
                "stimCoord and/or stimCoord2 have incorrect dimensions"

        self.dt=0.05
        
        count = mp.Value('i',0)
        
        p = [0] * self.N
#        res =  [0] * self.N

        shp = list(self.mdl.Y.shape[:-1])
        shp.append(round(tmax/(self.dt*20))+1)

        self.Vm = shmarray.zeros(shp, numpy.float)
        self.t = shmarray.zeros(round(tmax/(self.dt*20))+1, numpy.float)
        s_mutex = mp.Semaphore(1)
        s_attente = mp.Semaphore(0)
        
        print 'nombre de processus : ' + str(self.N)

        for n in range(self.N): 
            if profiling:
                p[n] = mp.Process(target=profilepara, args = 
        (n,tmax,Nx,Ny,Nz,self.N,stimCoord,stimCoord2,self.mdl.getlistparams(),
        self.Iamp,self.dt,self.Y,self.mdl.mask,count,self.Vm,self.t,s_mutex,
        s_attente))
            else:
                p[n] = mp.Process(target=parallelcompMP, args = 
        (n,tmax,Nx,Ny,Nz,self.N,stimCoord,stimCoord2,self.mdl.getlistparams(),
        self.Iamp,self.dt,self.Y,self.mdl.mask,count,self.Vm,self.t,s_mutex,
        s_attente))
            p[n].start()

        p[0].join()


class IntPara(IntGen):
    """Integrator class using parallel computation"""

    def __init__(self,mdl):
        """The constructor.
                mdl : model (of class Red3 or Red6)
        """
        assert HASMPI, "mpi does not seem to be present in your system.. sorry!"
        IntGen.__init__(self,mdl)
        #find the engine processes
        rc = Client(profile='mpi')
        rc.clear()
        #Create a view of the processes
        self.view = rc[:]

        def foo():
            import cell_mdl
            from mpi4py import MPI

        self.view.apply_sync(foo)

        #number of clients
        nCl = len(rc.ids)

        if mdl.Y.ndim >2:
            #divisors of nCl
            div = [i for i in range(1,nCl+1) if nCl%i==0]
            ldiv = len(div)
            #the surface will be divided into nbx rows and nby columns
            if ldiv %2 == 0:
                self.nbx = div[ldiv/2]
                self.nby = div[ldiv/2-1]
            else:
                self.nbx = self.nby = div[ldiv/2]
        else:
            self.nbx = nCl
            self.nby = 0

    def compute(self,tmax=500,stimCoord=-1,stimCoord2=-1):
        """Compute.
                tmax : maximum duration (in ms)
                stimCoord,stimCoord2 : Coordinates of the stimulations
        """

        def parallelcomp(tmax,Nx,Ny,Nz,nbx,nby,stimCoord,stimCoord2,listparam,
                                                                    Iamp,dt):
            """Function used by the engine processes"""            

            import cell_mdl
            from mpi4py import MPI

            def findlimitsx(rank,nbx,Nx):
                newNxx = round( (Nx + (nbx-1) * 2) / (nbx) )
                x = [0,0]
                if (rank%nbx==0):
                    x = [0,newNxx]
                elif rank%nbx==(nbx-1):
                    x = [rank%nbx * newNxx - rank%nbx,Nx]
                    newNxx = x[1] - x[0]
                else:
                    x[0] = rank%nbx * newNxx - rank%nbx
                    x[1] = x[0] + newNxx

                return x,newNxx

            def findlimitsy(rank,nby,Ny,nbx):
                newNyy = round( (Ny + (nby-1) * 2) / (nby) )
                y = [0,0]
                if (rank/nbx==0):
                    y = [0,newNyy]
                elif (rank/nbx==(nby-1)):
                    y = [rank/nbx * newNyy - rank/nbx,Ny]
                    newNyy = y[1] - y[0]
                else:
                    y[0] = rank/nbx * newNyy - rank/nbx
                    y[1] = y[0] + newNyy
                return y,newNyy


            rank = MPI.COMM_WORLD.Get_rank()
            # Which rows should I compute?
            [x,newNx] = findlimitsx(rank,nbx,Nx+4)

            #Stimulation (global coordinates)
            xyIstim1 = stimCoord 
            xyIstim2 = stimCoord2

            #computing the local coordinates
            if (xyIstim1[0] > x[-1]) or (xyIstim1[1] < x[0]):
                xyIstim1[0:2] = [-1,-1]
            else:
                xyIstim1[0:2] = [max(xyIstim1[0],x[0])-x[0],
                                min(xyIstim1[1],x[-1])-x[0]]

            if (xyIstim2[0] > x[-1]) or (xyIstim2[1] < x[0]):
                xyIstim2[0:2] = [-1,-1]
            else:
                xyIstim2[0:2] = [max(xyIstim2[0],x[0])-x[0],
                                min(xyIstim2[1],x[-1])-x[0]]

            # What about the columns?
            if Ny:
                [y,newNy] = findlimitsy(rank,nby,Ny+4,nbx)

                if (xyIstim1[2] > y[-1]) or (xyIstim1[3] < y[0]):
                    xyIstim1[2:4] = [-1,-1]
                else:
                    xyIstim1[2:4] = [max(xyIstim1[2],y[0])-y[0],
                                    min(xyIstim1[3],y[-1])-y[0]]

                if (xyIstim2[2] > y[-1]) or (xyIstim2[3] < y[0]):
                    xyIstim2[2:4] = [-1,-1]
                else:
                    xyIstim2[2:4] = [max(xyIstim2[2],y[0])-y[0],
                                    min(xyIstim2[3],y[-1])-y[0]]
                
                Ny2 = newNy-2*(rank/nbx==0)-2*(rank/nbx==(nby-1))
            else:  
                y = 0
                Ny2 = 0
            

            #Creation of the model (one for each process)
            mpi=[(rank%nbx==0),rank%nbx==(nbx-1),(rank/nbx==0),
                (rank/nbx==(nby-1)),True,True]
            if listparam['Name'] == 'Red6':
                mdl=cell_mdl.Red6(
        Nx=newNx-2*(rank%nbx==0)-2*(rank%nbx==(nbx-1)),Ny=Ny2,Nz=Nz,borders=mpi
                                 )
            elif listparam['Name'] == 'Red3':
                mdl=cell_mdl.Red3(
        Nx=newNx-2*(rank%nbx==0)-2*(rank%nbx==(nbx-1)),Ny=Ny2,Nz=Nz,borders=mpi
                                 )
            mdl.setlistparams(listparam)
            mdl.Name += 'p'

            def modify(var,x,y):
                if not(isinstance(var,int)) and not(isinstance(var,float)):
                    if var.ndim == 1:
                        return var[x[0]:x[1]]
                    elif var.ndim == 2:
                        return var[x[0]:x[1],y[0]:y[1]]
                    else:
                        return var[x[0]:x[1],y[0]:y[1],:]
                else:
                    return var

            mdl.masktempo = modify(mdl.masktempo,x,y)
            mdl.hx = modify(mdl.hx,x,y)
            mdl.hy = modify(mdl.hy,x,y)
            mdl.hz = modify(mdl.hz,x,y)
            mdl.Rax = modify(mdl.Rax,x,y)
            mdl.Ray = modify(mdl.Ray,x,y)
            mdl.Raz = modify(mdl.Raz,x,y)

            #Tells the model where the stimuli are
            if xyIstim1[0] != -1 and (Ny and xyIstim1[2] != -1):
                mdl.stimCoord = xyIstim1
            if xyIstim2[0] != -1 and (Ny and xyIstim2[2] != -1):
                mdl.stimCoord2 = xyIstim2

            def _stim1(mdl,stimCoord,Ist):
                if stimCoord[0] != -1:
                    mdl.Istim[stimCoord[0]:stimCoord[1]]=Ist

            def _stim2(mdl,stimCoord,Ist):
                if stimCoord[0] != -1 and stimCoord[2] != -1:
                    mdl.Istim[stimCoord[0]:stimCoord[1],
                              stimCoord[2]:stimCoord[3]]=Ist

            def _stim3(mdl,stimCoord,Ist):
                if stimCoord[0] != -1 and stimCoord[2] != -1:
                    mdl.Istim[stimCoord[0]:stimCoord[1],
                              stimCoord[2]:stimCoord[3],
                              stimCoord[4]:stimCoord[5]]=Ist

            def _comm1(mdl,rank,test,nbx):
                from mpi4py import MPI
                to_send_1 = mdl.Y[0,0]
                to_send_2 = mdl.Y[-1,0]
                to_recv_1 = mdl.Y[-1,0]
                to_recv_2 = mdl.Y[0,0]
                if test[0]:
                    if test[1]:
                        MPI.COMM_WORLD.send(to_send_1 , dest=rank-1)
                    if test[2]:
                        to_recv_1 = MPI.COMM_WORLD.recv(source=rank+1)
                        MPI.COMM_WORLD.send(to_send_2, dest=rank+1)
                    if test[1]:
                        to_recv_2 = MPI.COMM_WORLD.recv(source=rank-1)
                else:
                    if test[2]:
                        to_recv_1 = MPI.COMM_WORLD.recv(source=rank+1)
                    if test[1]:
                        MPI.COMM_WORLD.send(to_send_1 , dest=rank-1)
                        to_recv_2 = MPI.COMM_WORLD.recv(source=rank-1)
                    if test[2]:
                        MPI.COMM_WORLD.send(to_send_2, dest=rank+1)	
                mdl.Y[-1,0] = to_recv_1 
                mdl.Y[0,0] =  to_recv_2

            def _comm2(mdl,rank,test,nbx):
                from mpi4py import MPI
                to_send_1 = mdl.Y[0,:,0]
                to_send_2 = mdl.Y[-1,:,0]
                to_recv_1 = mdl.Y[-1,:,0]
                to_recv_2 = mdl.Y[0,:,0]

                if test[0]:
                    if test[1]:
                        MPI.COMM_WORLD.send(to_send_1 , dest=rank-1)
                    if test[2]:
                        to_recv_1 = MPI.COMM_WORLD.recv(source=rank+1)
                        MPI.COMM_WORLD.send(to_send_2, dest=rank+1)
                    if test[1]:
                        to_recv_2 = MPI.COMM_WORLD.recv(source=rank-1)
                else:
                    if test[2]:
                        to_recv_1 = MPI.COMM_WORLD.recv(source=rank+1)
                    if test[1]:
                        MPI.COMM_WORLD.send(to_send_1 , dest=rank-1)
                        to_recv_2 = MPI.COMM_WORLD.recv(source=rank-1)
                    if test[2]:
                        MPI.COMM_WORLD.send(to_send_2, dest=rank+1)

                mdl.Y[-1,:,0] = to_recv_1
                mdl.Y[0,:,0] = to_recv_2

                #Communication y
                to_send_1 = mdl.Y[:,0,0]
                to_send_2 = mdl.Y[:,-1,0]
                to_recv_1 = mdl.Y[:,-1,0]
                to_recv_2 = mdl.Y[:,0,0]

                if test[0]:
                    if test[3]:
                        to_recv_2 = MPI.COMM_WORLD.recv(source=rank-nbx)
                    if test[4]:
                        MPI.COMM_WORLD.send(to_send_2, dest=rank+nbx)
                        to_recv_1 = MPI.COMM_WORLD.recv(source=rank+nbx)
                    if test[3]:
                        MPI.COMM_WORLD.send(to_send_1 , dest=rank-nbx)
                else:
                    if test[4]:
                        MPI.COMM_WORLD.send(to_send_2, dest=rank+nbx)
                    if test[3]:
                        to_recv_2 = MPI.COMM_WORLD.recv(source=rank-nbx)
                        MPI.COMM_WORLD.send(to_send_1 , dest=rank-nbx)
                    if test[4]:
                        to_recv_1 = MPI.COMM_WORLD.recv(source=rank+nbx)

                mdl.Y[:,-1,0] = to_recv_1
                mdl.Y[:,0,0] = to_recv_2

            def _comm3(mdl,rank,test,nbx):
                from mpi4py import MPI
                to_send_1 = mdl.Y[0,:,:,0]
                to_send_2 = mdl.Y[-1,:,:,0]
                to_recv_1 = mdl.Y[-1,:,:,0]
                to_recv_2 = mdl.Y[0,:,:,0]

                if test[0]:
                    if test[1]:
                        MPI.COMM_WORLD.send(to_send_1 , dest=rank-1)
                    if test[2]:
                        to_recv_1 = MPI.COMM_WORLD.recv(source=rank+1)
                        MPI.COMM_WORLD.send(to_send_2, dest=rank+1)
                    if test[1]:
                        to_recv_2 = MPI.COMM_WORLD.recv(source=rank-1)
                else:
                    if test[2]:
                        to_recv_1 = MPI.COMM_WORLD.recv(source=rank+1)
                    if test[1]:
                        MPI.COMM_WORLD.send(to_send_1 , dest=rank-1)
                        to_recv_2 = MPI.COMM_WORLD.recv(source=rank-1)
                    if test[2]:
                        MPI.COMM_WORLD.send(to_send_2, dest=rank+1)

                mdl.Y[-1,:,:,0] = to_recv_1
                mdl.Y[0,:,:,0] = to_recv_2

                #Communication y
                to_send_1 = mdl.Y[:,0,:,0]
                to_send_2 = mdl.Y[:,-1,:,0]
                to_recv_1 = mdl.Y[:,-1,:,0]
                to_recv_2 = mdl.Y[:,0,:,0]

                if test[0]:
                    if test[3]:
                        to_recv_2 = MPI.COMM_WORLD.recv(source=rank-nbx)
                    if test[4]:
                        MPI.COMM_WORLD.send(to_send_2, dest=rank+nbx)
                        to_recv_1 = MPI.COMM_WORLD.recv(source=rank+nbx)
                    if test[3]:
                        MPI.COMM_WORLD.send(to_send_1 , dest=rank-nbx)
                else:
                    if test[4]:
                        MPI.COMM_WORLD.send(to_send_2, dest=rank+nbx)
                    if test[3]:
                        to_recv_2 = MPI.COMM_WORLD.recv(source=rank-nbx)
                        MPI.COMM_WORLD.send(to_send_1 , dest=rank-nbx)
                    if test[4]:
                        to_recv_1 = MPI.COMM_WORLD.recv(source=rank+nbx)

                mdl.Y[:,-1,:,0] = to_recv_1
                mdl.Y[:,0,:,0] = to_recv_2


            decim=20
            NbIter=0
#            Ft = 0.15

            time=numpy.zeros(round(tmax/(dt*decim))+1)

            if Nx*Ny*Nz:
                Vm=numpy.zeros((mdl.Nx,mdl.Ny,mdl.Nz,round(tmax/(dt*decim))+1))
                stim = _stim3
                comm = _comm3
                test = [rank%2,rank%nbx != 0,rank%nbx != nbx-1,
                        rank/nbx != 0,rank/nbx != nby-1]
            elif Nx*Ny:
                Vm=numpy.zeros((mdl.Nx,mdl.Ny,round(tmax/(dt*decim))+1))
                stim = _stim2
                comm = _comm2
                test = [rank%2,rank%nbx != 0,rank%nbx != nbx-1,
                        rank/nbx != 0,rank/nbx != nby-1]
            elif Nx:
                Vm=numpy.zeros((mdl.Nx,round(tmax/(dt*decim))+1))
                stim = _stim1
                comm = _comm1
                test = [rank%2,rank%nbx != 0,rank%nbx != nbx-1]
            
            mdl.flag = True
            mdl.time = 0


            while (mdl.time<tmax):
                Ist=Iamp/2*(numpy.sign(numpy.sin(
                        2*numpy.pi*mdl.time/(2*tmax))
                        )+1)*numpy.sin(2*numpy.pi*mdl.time/(2*tmax))

                if (mdl.time != 0) and (Ist == 0):
                    mdl.flag = False
                stim(mdl,xyIstim1,Ist)
                stim(mdl,xyIstim2,Ist)

                mdl.derivT(dt)
                comm(mdl,rank,test,nbx)
                        
                mdl.time +=dt
                if not round(mdl.time/dt)%decim:
                    NbIter+=1
                    time[NbIter]=mdl.time
                    if Nx*Ny*Nz:
                        Vm[:,:,:,NbIter]=mdl.Y[:,:,:,0].copy()
                    elif Nx*Ny:
                        Vm[:,:,NbIter]=mdl.Y[:,:,0].copy()
                    elif Nx:
                        Vm[:,NbIter]=mdl.Y[:,0].copy()

            return {'rank':rank,'time':time,'x':x,'y':y,'Vm':Vm}

        try: Nz = self.mdl.Nz - self.mdl.Padding
        except AttributeError: Nz = 0

        try: Ny = self.mdl.Ny - self.mdl.Padding
        except AttributeError: Ny = 0

        Nx = self.mdl.Nx - self.mdl.Padding

        if stimCoord == -1:
            stimCoord = self.mdl.stimCoord
        else:
            self.mdl.stimCoord = stimCoord

        if stimCoord2 == -1:
            stimCoord2 = self.mdl.stimCoord2
        else:
            self.mdl.stimCoord2 = stimCoord2


        assert (self.mdl.Y.ndim - 1 == len(stimCoord)/2) and \
                (self.mdl.Y.ndim - 1 == len(stimCoord2)/2), \
                "stimCoord and/or stimCoord2 have incorrect dimensions"


        self.dt=0.05
        res = self.view.apply_async(parallelcomp,tmax,Nx,Ny,Nz,self.nbx,
    self.nby,stimCoord,stimCoord2,self.mdl.getlistparams(),self.Iamp,self.dt)

        self.view.wait(res)  #wait for the results
        tabResults = res.get()


#        tabResults  = self.view.apply_sync(parallelcomp,tmax,Nx,Ny,Nz,self.nbx,
#    self.nby,stimCoord,stimCoord2,self.mdl.getlistparams(),self.Iamp,self.dt)

        self.t = tabResults[0]['time']

        tabrank = numpy.empty(len(tabResults))

        for i in range(len(tabResults)):
            tabrank[i] = tabResults[i]['rank']

        def find(f, seq):
            comp = 0
            for item in seq:
                if item == f: 
                    return comp
                comp += 1
            return -1

#        v = tabResults[0]['Vm']

        # Aggregation of the results
        if Nx*Ny*Nz:
            self.Vm = numpy.empty((Nx+self.mdl.Padding,Ny+self.mdl.Padding,
                                            Nz+self.mdl.Padding,len(self.t)))
        elif Nx*Ny:
            self.Vm = numpy.empty((Nx+self.mdl.Padding,Ny+self.mdl.Padding,
                                                                len(self.t)))
        elif Nx:
            self.Vm = numpy.empty((Nx+self.mdl.Padding,len(self.t)))

        for i in range(len(tabrank)):
            i_client = find(i, tabrank)
            x = tabResults[i_client]['x']
            y = tabResults[i_client]['y']
            if y:
                self.Vm[x[0]:x[1],y[0]:y[1],...] = \
                                        numpy.array(tabResults[i_client]['Vm'])
            else:
                self.Vm[x[0]:x[1],:] = numpy.array(tabResults[i_client]['Vm'])

        self.t = self.t[...,1:]
        self.Vm = self.Vm[...,1:]

        return self.t,self.Vm
