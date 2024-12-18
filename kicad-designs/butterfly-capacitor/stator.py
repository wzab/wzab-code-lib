#!/usr/bin/env python3
#Constants
bd_h = 120 #Board height in mm
bd_w = 100 #Board width in mm
pad_r = 50 #Inner pad diameter in mm
pad_r2 = 15 #Inner pad diameter in mm
pad_ang = 80 # Pad angle in degrees
cof = 10 # Assembly cut-off size
import pcbnew
import math
bd = pcbnew.CreateEmptyBoard()

#Convert angles
def a2k(angle):
    return angle*math.pi/180
#Convert coordinates
def c2k(coord):
    return int(1000000*coord)

def arc_point(r,ang):
    x = c2k(r*math.sin(a2k(ang)))
    y = c2k(r*math.cos(a2k(ang)))
    return (x,y)
    
#Add the board boundary
cntr = pcbnew.VECTOR2I(0,0)

c1 = pcbnew.SHAPE_LINE_CHAIN()
c1.Append(-c2k((bd_w+1)/2),-c2k((bd_h+1)/2))
c1.Append(-c2k((bd_w+1)/2),c2k((bd_h+1)/2))
c1.Append(c2k((bd_w+1)/2),c2k((bd_h+1)/2))
#Create the assembly cut-off
c1.Append(c2k((bd_w+1)/2),c2k(cof/2))
c1.Append(c2k(0),c2k(cof/2))
npts = 40
for i in range(0,npts+1):
    (x,y) = arc_point(cof/2,180/npts*i)            
    c1.Append(-x,y)
c1.Append(c2k(0),-c2k((cof)/2))
c1.Append(c2k((bd_w+1)/2),c2k(-(cof)/2))
#
c1.Append(c2k((bd_w+1)/2),-c2k((bd_h+1)/2))
c1.Append(-c2k((bd_w+1)/2),-c2k((bd_h+1)/2))
c1.SetClosed(True)
s0 = pcbnew.SHAPE_POLY_SET()
s0.AddOutline(c1)            
s1 = pcbnew.PCB_SHAPE(bd,pcbnew.SHAPE_T_POLY)
s1.SetPolyShape(s0)
s1.SetWidth(c2k(1))
s1.SetFilled(False)
s1.SetLayer(pcbnew.Edge_Cuts)
bd.Add(s1)

# Created a hole for the shaft
module = pcbnew.FOOTPRINT(bd)
pad = pcbnew.PAD(module)
pad.SetSize(pcbnew.VECTOR2I(c2k(5),c2k(5)))
pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
pad.SetLayerSet(pad.PTHMask())
pad.SetDrillSize(pcbnew.VECTOR2I(c2k(5),c2k(5)))
pad.SetName('')
module.Add(pad)
bd.Add(module)

# Create the rotor plates    
for lay in [pcbnew.F_Cu, pcbnew.B_Cu]:
    for sy in [-1,1]:
        c1 = pcbnew.SHAPE_LINE_CHAIN()
        c1.Append(-c2k((bd_w-5)/2),sy*c2k((bd_h-5)/2))
        c1.Append(-c2k((bd_w-5)/2),sy*c2k(pad_r))        
        npts = 20
        for i in range(-npts,npts+1):
            (x,y) = arc_point(pad_r2,pad_ang/2/npts*i)            
            c1.Append(x,sy*y)
        c1.Append(c2k((bd_w-5)/2),sy*c2k(pad_r))                    
        c1.Append(c2k((bd_w-5)/2),sy*c2k((bd_h-5)/2))
        c1.SetClosed(True)
        s1 = pcbnew.SHAPE_POLY_SET()
        s1.AddOutline(c1)            
        b2 = pcbnew.PCB_SHAPE(bd, pcbnew.SHAPE_T_POLY)
        b2.SetPolyShape(s1)
        b2.SetWidth(c2k(5))
        b2.SetFilled(True)
        b2.SetLayer(lay)
        bd.Add(b2)

#Add mounting pads
for (x,y) in [
  (-c2k((bd_w-12)/2),-c2k((bd_h-12)/2)),
  (-c2k((bd_w-12)/2),c2k((bd_h-12)/2)),
  (c2k((bd_w-12)/2),-c2k((bd_h-12)/2)),
  (c2k((bd_w-12)/2),c2k((bd_h-12)/2))
  ]:
  module = pcbnew.FOOTPRINT(bd)
  pad = pcbnew.PAD(module)
  pad.SetSize(pcbnew.VECTOR2I(c2k(12),c2k(12)))
  pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
  pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
  pad.SetLayerSet(pad.PTHMask())
  pad.SetDrillSize(pcbnew.VECTOR2I(c2k(4),c2k(4)))
  pad.SetName('')
  module.Add(pad)
  module.SetX(x)
  module.SetY(y)
  bd.Add(module)

pcbnew.Refresh()

bd.Save("stator.kicad_pcb")

