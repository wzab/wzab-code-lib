--[[
Script that reformats the C source code 
passing it via external command 
defined in variable "flt"
--]]
local flt = "astyle --indent-classes -Y"
line, column = geany.rowcol()
local fn=os.tmpname()
local fo=assert(io.open(fn,'w'))
assert(fo:write(geany.text()))
fo:close()
local cmd = "cat ".. fn .. " | " .. flt
local f = assert(io.popen(cmd, 'r'))
local s = assert(f:read('*a'))
f:close()
os.remove(fn)
geany.text(s)
position=geany.rowcol(line,column)
geany.caret(position)
