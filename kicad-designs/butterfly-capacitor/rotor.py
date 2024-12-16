#!/usr/bin/env python3
#Constants
bd_r = 50 #Board diameter in mm
pad_r = 45 #Pad diameter in mm
pad_ang = 80 # Pad angle in degrees

import pcbnew
import math
bd = pcbnew.CreateEmptyBoard()

#Convert angles
def a2k(angle):
    return angle*math.pi/180
#Convert coordinates
def c2k(coord):
    return int(1000000*coord)

#Add the board boundary
cntr = pcbnew.VECTOR2I(0,0)
top = pcbnew.VECTOR2I(c2k(0),c2k(bd_r))
bot = pcbnew.VECTOR2I(c2k(0),c2k(-bd_r))
c1 = pcbnew.PCB_SHAPE()
c1.SetShape(pcbnew.S_CIRCLE)
c1.SetCenter(cntr)
#c1.SetStart(top)
c1.SetEnd(top)
c1.SetWidth(c2k(1))
c1.SetLayer(pcbnew.Edge_Cuts)
bd.Add(c1)

def arc_point(r,ang):
    x = c2k(r*math.sin(a2k(ang)))
    y = c2k(r*math.cos(a2k(ang)))
    return (x,y)

# Create the rotor plates    
for lay in [pcbnew.F_Cu, pcbnew.B_Cu]:
    for sy in [-1,1]:
        c1 = pcbnew.SHAPE_LINE_CHAIN()
        c1.Append(0,0)
        npts = 20
        for i in range(-npts,npts+1):
            (x,y) = arc_point(pad_r,pad_ang/2/npts*i)            
            c1.Append(x,sy*y)
        c1.Append(0,0)
        c1.SetClosed(True)
        s1 = pcbnew.SHAPE_POLY_SET()
        s1.AddOutline(c1)            
        b2 = pcbnew.PCB_SHAPE(bd, pcbnew.SHAPE_T_POLY)
        b2.SetPolyShape(s1)
        b2.SetWidth(c2k(5))
        b2.SetFilled(True)
        b2.SetLayer(lay)
        bd.Add(b2)

#Add the central pad
module = pcbnew.FOOTPRINT(bd)
bd.Add(module)
pad = pcbnew.PAD(module)
pad.SetSize(pcbnew.VECTOR2I(c2k(12),c2k(12)))
pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
pad.SetLayerSet(pad.PTHMask())
pad.SetDrillSize(pcbnew.VECTOR2I(c2k(4),c2k(4)))
pad.SetName('')
module.Add(pad)

pcbnew.Refresh()

bd.Save("rotor.kicad_pcb")

