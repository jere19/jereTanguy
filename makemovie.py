import numpy
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
try:
    from scipy import io
except: pass
import cPickle
import subprocess
import os
import sys
try:
    from progressbar import Bar,ProgressBar,Percentage
    showbar=True
except:
    showbar=False

def usage():
    print "Usage:"
    print "If matlab file :\n\t"+sys.argv[0]+" -m datafile.mat [dt]"
    print "If pickled Python objects :\n\t"+sys.argv[0]+" -p datafile.dat [dt]"
    print "If compressed numpy objects :\n\t"+sys.argv[0]+" -n datafile.npz [dt]"
    print "If numpy objects :\n\t"+sys.argv[0]+" -y datafile-Y.npy [dt]"
    print "                      datafile-t.npy must be present"
    print "Optional argument : dt, time in ms between images"  
    
def loadsignal():
    datafile = sys.argv[2]
    #Managing file types
    if sys.argv[1]=='-m':
        var=io.loadmat(datafile)
        t=var['t']
        Y=var['Y']
        dataext='.mat'
    elif sys.argv[1]=='-p':
        ofile=open(datafile)
        (t,Y)=cPickle.load(ofile)
        ofile.close()
        dataext='.dat'
    elif sys.argv[1]=='-n':
        ofile=open(datafile)
        npztmp=numpy.load(ofile)
        t=npztmp['t']
        Y=npztmp['Y']
        ofile.close()
        dataext='.npz'
    elif sys.argv[1]=='-y':
        Y=numpy.load(datafile,mmap_mode='r')

        datafile_t = datafile.replace('-Y.npy','-t.npy')
        if datafile_t == datafile:
            usage()
            sys.exit(2)
        
        t=numpy.load(datafile_t,mmap_mode='r')
        dataext='.npy'
    else:
        usage()
        sys.exit(2)
    return t,Y,datafile,dataext

def newY1(Y,i):
    nY=Y[...,i]
    return nY

def newY2(Y,i): 
    nY=Y[i]
    return nY





#Test if correct number of arguments
if not(len(sys.argv)==3 or len(sys.argv)==4):
    usage()
    sys.exit()
    
    
#Test if tmp png dir exist, else create it
if not(os.path.isdir('png/')):
       os.mkdir('png/')

t,Y,datafile,dataext=loadsignal()  
  
if (len(sys.argv)==4):
    tstep=int(sys.argv[3])
else:
    tstep=10

#Dealing with varations of variable formats
if t.size==Y.shape[2]:
    yda=0
    ydb=1
    newY=newY1

elif t.size==Y.shape[0]:
    yda=1
    ydb=2
    newY=newY2

else:
    print "Format unknown for Y."
        

#Choose appropriate plot options according to Y dimensions 
if (Y.shape[yda]*2>Y.shape[ydb]):
    cbopts=dict(pad=0.1)
    figy=6    
else:
    cbopts=dict(pad=0.1, orientation='horizontal')
    figy=3


print "Writing png files from "+sys.argv[2]
if showbar:
    pbar = ProgressBar(widgets=[Percentage(), Bar()], maxval=len(t)).start()

#print files
i=0
plt.figure(1,figsize=(8, figy))
im=plt.imshow(newY(Y,i),vmin=-60,vmax=10)
#
# Notice the use of LaTeX-like markup.
#
plt.title(str("Potential at time: %.0f ms."% t[i]), fontsize=20)
cb=plt.colorbar(**cbopts)
cb.ax.set_xlabel('mV')
#
# The file name indicates how the image will be saved and the
# order it will appear in the movie.  If you actually wanted each
# graph to be displayed on the screen, you would include commands
# such as show() and draw() here.  See the matplotlib
# documentation for details.  In this case, we are saving the
# images directly to a file without displaying them.
#
filename = str('png/2F_%04d' % i) + '.png'
plt.savefig(filename, dpi=100)



for i in range(int(tstep/round(max(t)/len(t))),len(t),int(tstep/round(max(t)/len(t)))) :
    #
    # The next four lines are just like MATLAB.
    #
    im.set_data(newY(Y,i))
    plt.title(str("Potential at time: %.0f ms."% t[i]), fontsize=20)
    #
    # Let the user know what's happening.
    #
    #print 'Wrote file', filename
    filename = str('png/2F_%04d' % i) + '.png'
    plt.savefig(filename, dpi=100)
    #
    # Clear the figure to make way for the next image.
    if showbar:
        pbar.update(i)

    
if showbar:    
    pbar.finish()
# Now that we have graphed images of the dataset, we will stitch them
# together using Mencoder to create a movie.  Each image will become
# a single frame in the movie.
#
# We want to use Python to make what would normally be a command line
# call to Mencoder.  Specifically, the command line call we want to
# emulate is (without the initial '#'):
# mencoder mf://*.png -mf type=png:w=800:h=600:fps=25 -ovc lavc -lavcopts vcodec=mpeg4 -oac copy -o output.avi
# See the MPlayer and Mencoder documentation for details.
#
vidfile=datafile.replace(dataext,'.avi')
command = ('mencoder',
           'mf://png/2F*.png',
           '-mf',
           'type=png:w=800:h=%d:fps=25'%(figy*100),
           '-ovc',
           'lavc',
           '-lavcopts',
           'vcodec=mpeg4',
           '-oac',
           'copy',
           '-o',
           vidfile)

#os.spawnvp(os.P_WAIT, 'mencoder', command)

print "\n\nabout to execute:\n%s\n\n" % ' '.join(command)
subprocess.check_call(command)

print "\n\n The movie was written to "+vidfile


#Ask to delete tmp png files
if raw_input('Delete *.png files (y/N)? ')=="y":
    os.popen('rm png/2F_*')

#exists 
