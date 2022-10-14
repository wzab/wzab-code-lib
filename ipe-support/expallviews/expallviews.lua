-- This is the script for exporting all views from all pages 
-- in the IPE drawing. 
-- I use it to export animated figures for beamer presentations.
-- The names of generated files allow to easy inclusion with
-- \multiinclude
-- If your file is named "myfile.ipe", you may prepare animation
-- based on views of page 1 with:
-- \multiinclude[<+>][format=pdf,start=1,graphics={width=0.9\linewidth}]{myfile-p-1-v}
--
-- Based on the information from 
-- http://ipe.otfried.org/manual/luapage.html
-- This script was written by Wojciech M. Zabolotny
-- ( wzab01<at>gmail.com )
-- and is published as Public Domain or under
-- Creative Commons CC0 license, whatever better suits your needs. 
-- 
if #argv ~= 2 then
  io.stderr:write("Usage: ipescript expallviews <inputfile> <outputdir>\n")
  return
end
fname=argv[1]
print(fname)
doc = ipe.Document(fname)
doc:runLatex()
-- Prepare the base file name for the output files
-- Remove the directory part (if exists)
fbase=fname:reverse()
-- reverse the string. to make searching for last "/" and "." easier
i = fbase:find("/",1,"plain")
if (i) then
  fbase=fbase:sub(1,i-1)
end 
i = fbase:find(".",1,"plain")
if (i) then
  fbase=fbase:sub(i+1)
end
fbase=fbase:reverse()
-- Add the output directory to the base filename
fbase=argv[2] .. "/" .. fbase 
-- Now we can convert all the views from all pages
np=#doc
--print(fname .. " contains " .. np )
flags={}
flags["export"]=false
flags["nozip"]=0
for p=1,np,1
do
  pg=doc[p]
  nv = pg:countViews()
  --print(fname .. " page " .. p .. " contains " ..  nv .. " views")
  for v=1,nv,1
  do
    fout=fbase .. "-p-" .. p .. "-v-" .. v .. ".pdf"
    --print("exporting to: " .. fout)
    os.execute("iperender -pdf -page " .. p .. " -view " .. v .. " " .. fname .. " " .. fout)
  end
end

