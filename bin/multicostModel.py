#!/usr/bin/env python
import os
import sys
import time
sys.path += ['..']
from glob import iglob
from leamsite import LEAMsite
from parameters import *
from genSimMap import genSimMap, genclassColorCondlist

"""Organized from original LEAM attrmap.make and probmap.make.
"""

# Used for publish simmap onto the site
resultsdir = sys.argv[1]
user = sys.argv[2]
passwd = sys.argv[3]

site = LEAMsite(resultsdir, user, passwd)

######################## Basic GRASS and site setup Functions #################################
def grassConfig(location, mapset,
    gisbase='/usr/local/grass-6.4.5svn', gisdbase='.'):
    """ Set grass environment to run grass.script as grass
    """
    os.environ['GISBASE'] = gisbase
    os.environ['GRASS_VERBOSE'] = '0'
    os.environ['GRASS_OVERWRITE'] = '1'
    sys.path.append(os.path.join(gisbase, 'etc', 'python'))

    global grass
    __import__('grass.script')
    grass = sys.modules['grass.script']
    from grass.script.setup import init
    gisrc = init(gisbase, gisdbase, location, mapset)  


def importVector(fullpathfilename, layername):
    if grass.run_command('v.in.ogr', flags='o', dsn=fullpathfilename,
            snap='0.01', output=layername, overwrite=True, quiet=True):
        raise RuntimeError('unable to import vectormap ' + layername) 


def exportRaster(layername, valuetype='Float64'): #'UInt16'
    outfilename = 'Data/'+layername+'.tif'
    if grass.run_command('r.out.gdal', input=layername, 
      output=outfilename, type=valuetype):
        raise RuntimeError('unable to export raster map ' + layername )


def export_asciimap(layername, nullval=-1):
    """Export a raster layer into asciimap. The output folder is 'Data/'.
       @param: layername is the raster layer name.
    """
    outfilename = 'Data/'+layername+'.txt'
    if grass.run_command('r.out.ascii', input=layername, output=outfilename, null=nullval):
        raise RuntimeError('unable to export ascii map ' + layername)


def publishSimMap(maptitle, description='', numcolors=NUMCOLORS, 
    site=site, url=resultsdir, regioncode=CHICAGOREGIONCODE):
    simmap  = 'Data/%s.tif' % maptitle
    mapfile = 'Outputs/%s.map' % maptitle

    if (numcolors < 2):
        print "Error: number of baskets is less than 2. publish SimMap abort."
        return

    classColorCondlist = genclassColorCondlist(maptitle, numcolors)
    genSimMap(regioncode, classColorCondlist, maptitle)

    popattrurl = site.putSimMap("%s.tif" % maptitle, "%s.map" % maptitle, url,
        simmap_file=open(simmap, 'rb'), 
        mapfile_file=open(mapfile, 'rb'))
    site.updateSimMap(popattrurl, title=maptitle, description=maptitle)


def exportAllforms(mapfile):
    exportRaster(mapfile, 'Float64')
    export_asciimap(mapfile)
    publishSimMap(mapfile)

################## Fucntions for centers and travel time maps #################
######  Required files in GRASS: otherroadsBase, landcover ########
def genotherroads():
    """Vector map otherroads to raster map with value = class
    """
    grass.run_command('v.to.rast', input='otherroads', 
        output='otherroadsBase', column='class')
    grass.run_command('r.null', map='otherroadsBase', null=0)
    grass.mapcalc('otherroads=if(otherroadsBase==0,0,otherroadsBase)')
    grass.run_command('g.remove', rast="otherroadsBase")

def gencross():
    grass.run_command('g.remove', rast=["cross","intbuf"])
    # interstatesBase -> interstates
    grass.mapcalc('interstates=if(interstatesBase==0,0,1)')
    # interstates, otherroads -> cross
    grass.run_command('r.buffer',flags='z', input='interstates',
        output='intbuf', dist=60)
    grass.mapcalc('cross=if(intbuf && otherroads==6, 1, 0)')


def geninterstatesBase():
    grass.run_command('v.extract', input='otherroads',
        output='interstatesBase', where="class = 1")
    grass.run_command('v.to.rast', input='interstatesBase', 
        output='interstatesBase', column='class')
    grass.run_command('r.null', map='interstatesBase', null=0)


def genoverlandTravelTime30():
    """Generate traveltime map: overlandTravelTime30
       @input maps: landcover, otherroads interstatesBase
       @intermediate maps: landTravelSpeed30, othTravelSpeed30, interstates, 
                           overlandTravelSpeed30
       @output map: overlandTravelTime30 
    """
    grass.run_command('g.region', res=30)

    # landcover -> landTravelSpeed30
    grass.run_command('r.recode', input="landcover", 
        output="landTravelSpeed30", rules=GRAPHS+"/lu_speeds.recode")
    # otherroads ->otherroadsSpeedBase = othTravelSpeed30
    grass.run_command('v.to.rast', input="otherroads", 
        output="othTravelSpeed30", col="speed")

    # interstatesBase -> interstates
    grass.mapcalc ("interstates=if(interstatesBase==0,null(),1)")
    
    # othTravelSpeed30, landTravelSpeed30, interstates -> overlandTravelSpeed30
    grass.mapcalc("overlandTravelSpeed30=if(othTravelSpeed30, \
        othTravelSpeed30,if(interstates,0,landTravelSpeed30))")
    # overlandTravelSpeed30 -> overlandTravelTime30
    grass.mapcalc("overlandTravelTime30 =if($speed>0,1.8/$speed, null())", 
        speed="overlandTravelSpeed30")

    exportRaster('overlandTravelTime30')


def genintTravelTime30():
    """Gnereate traveltime map: intTravelTime30
       @input maps: interstatesBase
       @intermediate maps: intTravelSpeed30
       @output mpa: intTravelTime30
    """
    grass.run_command('g.region', res=30)
    
    # interstatesBase -> interstatesSpeedBase = intTravelSpeed30
    grass.run_command('v.to.rast', input="interstatesBase",
        output="intTravelSpeed30", col="speed")
    # intTravelSpeed30 -> intTravelTime30
    grass.mapcalc("intTravelTime30 =if($speed>0,1.8/$speed, null())", 
        speed="intTravelSpeed30")

    exportRaster('intTravelTime30')


def gencentersBuffer(centers, outfilename='ctmp'):
    """Generate a 6*6 buffer for centers
       @input maps: centers
       @intermediate maps: None
       @output map: outfilename
    """
    grass.run_command('g.region', res=30)

    grass.run_command('v.to.rast', input=centers, output=outfilename, 
        use='val', value=1, overwrite=True)

    grass.run_command('r.buffer', input=outfilename, output=outfilename, dist='180')
    grass.mapcalc(outfilename + '=if(' + outfilename +')')
    exportRaster(outfilename)


################# Multicost to Travel Time On Roads Model ###################
def multicost4travelcost(centersMap, outputname, maxcostmin):
    grass.run_command('r.multicost', input="overlandTravelTime30", 
        m2="intTravelTime30", xover="cross", start_rast=centersMap, 
        output=outputname, max_cost=maxcostmin)
    exportRaster(outputname)

################## Caculate Roads Attraction #################################
######  Required files in GRASS: otherroads #########
def roadsTravelCost(roadsClassName_list=[('staterd', 2), ('county', 3), ('road', 4), ('ramp', 6)]):
    """This takes about 3min.
    """
    for layername, classnum in roadsClassName_list:
        start = time.time()
        outname = str(layername)+"_cost"
        print "caculating " + outname + "..."
        grass.mapcalc('centers=if(otherroads==' + str(classnum) + ',1,null())')
        grass.run_command('r.multicost', input="overlandTravelTime30",
            m2="intTravelTime30", xover="cross", start_rast="centers", 
            output=outname)
        exportAllforms(outname)
        print outname," takes ", time.time()-start,"s."


def intersectionTravelCost(layername="intersect_cost"):
    """Finds state #2 and county #3 road  intersections.  Create a map of
       just state and county roads. Expand these locations by one cell and
       then thin them down to one cell (to take care of any small map errors).
       Then find cells that are surrounded by more than two cells containing
       roads.
    """
    grass.run_command('g.region', res=30)
    grass.mapcalc('int1=if((otherroads==2) || (otherroads==3), 1, 0)')
    grass.run_command('r.thin', input="int1", output="int2")
    grass.run_command('r.null', map="int2", null=0)
    grass.mapcalc('intersection=if(int2==1,  \
      if(2<(int2[-1,-1]+int2[-1,0]+int2[-1,1]+ \
            int2[ 0,-1]           +int2[ 0,1]+ \
            int2[ 1,-1]+int2[ 1,0]+int2[ 1,1]) ,1,0))')
    grass.run_command('r.null', map='intersection', setnull=0)
    

    grass.run_command('r.multicost', input="overlandTravelTime30",
            m2="intTravelTime30", xover="cross", start_rast="intersection", 
            output=layername)
    grass.run_command('g.remove', rast=["int1","int2", "intersection"])


def transportAttraction(layername="transport_att"):
    grass.mapcalc(layername+"="+str(W_STATERD)+"/(staterd_cost+0.1) + "
                               +str(W_COUNTY)+"/(county_cost+0.1) + "
                               +str(W_ROAD)+"/(road_cost+0.1) + "
                               +str(W_RAMP)+"/(ramp_cost+0.1) + "
                               +str(W_INTERSECT)+"/(intersect_cost+0.1)")
    grass.run_command('r.null', map=layername, null=0.0)

##################### Water and Forest Attraction ########################
######  Required files in GRASS: landcover #########
def watercondstr():
    return "(landcover==11)"
def forestcondstr():
    """41=deciduous forest, 42=evergreen forest, 43=mixed forest, 91=woody wetland"""
    return "(landcover==41 || landcover==42 || landcover==43 || landcover==91)"
def bufferAttraction(layername, layercond_str):
    grass.mapcalc('int1=if' + layercond_str)
    grass.run_command('r.buffer', flags='z', input='int1', output='int2',
       distances=[30,60,90,120,150,180,210,240,270,300,330,360])
    grass.mapcalc(layername+'=if(isnull(int2),390,(int2-1)*30)')
    grass.run_command('g.remove', rast=["int1","int2"])

##################### Slope Attraction ########################
######  Required files in GRASS: demBase #########
def slopeAttraction(layername="slope_att"):
    """Caculate slope attraction
       @input: demBase
       @output: slope_att
    """
    grass.run_command('r.slope.aspect', elevation="demBase", slope="int1")
    grass.mapcalc(layername+'=round(int1)')
    grass.run_command('g.remove', rast="int1")

##################### Transform Attrmaps to scores ######################
####### Required files: sfa files in ./SFA folder. ##########
def att2score(attname, scorename):
    """Transform attractiveness map to a score map using SFA files.
       @input: attractiveness map without _att
       @output: result score map name
    """
    grass.run_command('r.recode', input=attname+"_att", output=scorename+"_score", 
                                  rules="SFA/"+scorename+".sfa")
    # Setting to null so that there won't be weird values appear
    grass.run_command('r.null', map=scorename+"_score", null=0.0)
    return scorename+"_score"


def att2score_centers(attname, scorename):
    """Transform attractiveness map to a score map using SFA files.
       @input: attractiveness map without _att
       @output: result score map name
    """
    #if (scorename != 'pop_com' and scorename != 'pop_res'):
    grass.run_command('r.recode', input=attname+"_att", output=scorename+"_score", 
                                  rules="SFA/"+scorename+".sfa")
    export_asciimap(scorename+"_score")
    weight = WEIGHTS[scorename]
    grass.mapcalc('%s_score=pow(%s_score,%i)' %(scorename, scorename, weight))
    export_asciimap(scorename+"_score")
    return scorename+"_score"


def genProbmap(centerscorelist, attscorelist, problayername):
    """ From attrmaps to generate probmap.
        @input: centerscorelist is a list of (attname, scorename) pairs. 
                E.g. centerscorelist can be:
                [('pop', 'pop_com'), ('emp', 'emp_com'),
                 ('transport', 'transport_com')] for 'probmap_com' map.
                attlist can be [('forest', 'forest'), ('water', 'water'), ('slope', 'slope')]
        @output: probmap_com or probmap_res (commercial/residential)
    """
    grass.mapcalc(problayername+'=1.0')
    for att, score in attscorelist:
        score = att2score(att, score)
        grass.mapcalc(problayername +'='+ problayername + '*' + score)
    for att, score in centerscorelist:
        score = att2score_centers(att, score)
    grass.mapcalc(problayername +'='+ problayername + '*' + score)     
    grass.run_command('g.remove', rast=score)

##################### Main Functions to be called ######################
def gencentersAttmaps(empcenters, popcenters):
    # pop/emp centers attractive maps require landTravelTime30 and intTravelTime30
    # print "--generate otherroads..."
    # genotherroads()
    # print "--generate interstatesBase..."
    # geninterstatesBase()
    # print "--generate cross..."
    # gencross()
    # print "--generate overlandTravelTime30..."
    # genoverlandTravelTime30()
    # print "--generate landTravelTime30..."
    # genintTravelTime30()

    # TODO: gencentersBuffer should not use ctmp as output for both pop and emp
    
    # TODO: the genSimMap color has problems.
    # the centers has many 0 and 9999.
    # other costs has many -1.
    # slope_att = -1

    print "--generate population centers attractive map..."
    gencentersBuffer(POPCENTERS) 
    os.system("python bin/cities.py -p total_pop -n pop -m grav popcentersBase > Log/popatt.log")
    exportAllforms("pop_att")

    print "--generate population centers travelcost map..."
    os.system("python bin/cities.py -p total_pop -n pop -m cost popcentersBase > Log/popcost.log")
    exportAllforms("pop_cost")

    print "--generate employment centers attractive map..."
    gencentersBuffer(EMPCENTERS) 
    os.system("python bin/cities.py -p total_emp -n emp -m grav empcentersBase > Log/empatt.log")
    exportAllforms("emp_att")

    print "--generate employment centers travelcost map..."
    os.system("python bin/cities.py -p total_emp -n emp -m cost empcentersBase > Log/empcost.log")
    exportAllforms("emp_cost")


def genOtherAttmaps():
    print "--generate staterd, county, road, and ramp attractiveness..."
    roadsClassName_list = [('staterd', 2), ('county', 3), ('road', 4), ('ramp', 6)]    
    roadsTravelCost(roadsClassName_list)
    print "--generate intersection travel cost map..."
    intersectionTravelCost()
    exportAllforms("intersect_cost")
    print "--generate transport attraction map using statered_cost, county_cost, road_cost, ramp_cost, and intersect_cost..."
    transportAttraction()
    print "export transport attraction ascii map..."
    exportAllforms("transport_att")
    print "--generate water attraction map..."
    bufferAttraction("water_att", watercondstr())
    exportAllforms("water_att")
    print "--generate forest attraction map..."
    bufferAttraction("forest_att", forestcondstr())
    exportAllforms("forest_att")
    print "--generate slope attraction map..."
    exportAllforms("slope_att")


def genProbmaps():
    print "--generate probmap_com..."
    genProbmap(COMSCORELIST, ATTSCORELIST, 'probmap_com')
    exportAllforms('probmap_com')

    print "--generate probmap_res..."
    genProbmap(RESSCORELIST, ATTSCORELIST, 'probmap_res')
    exportAllforms('probmap_res')


def main():
    grassConfig('grass', 'model')
    
    # exportRaster('emp_centers4_47_98')
    # importVector('Data/FID4_47_98', EMPCENTERS) 
    # print "list available raster maps in database..."
    # grass.run_command('g.mlist', type='rast')   
    
    gencentersAttmaps(EMPCENTERS, POPCENTERS)
    genOtherAttmaps()
    genProbmaps()

    




     
if __name__ == "__main__":
    main()