import zipfile, re, posixpath
import xml.etree.ElementTree as ET
ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships','xdr':'http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing','a':'http://schemas.openxmlformats.org/drawingml/2006/main','pr':'http://schemas.openxmlformats.org/package/2006/relationships'}
def rels(z,path):
    d,f=posixpath.split(path); rp=posixpath.join(d,'_rels',f+'.rels')
    if rp not in z.namelist(): return {}
    return {e.get('Id'):posixpath.normpath(posixpath.join(d,e.get('Target'))) if not e.get('Target').startswith('/') else e.get('Target')[1:] for e in ET.fromstring(z.read(rp))}
def extract(xlsx):
    z=zipfile.ZipFile(xlsx); wb=ET.fromstring(z.read('xl/workbook.xml')); wr=rels(z,'xl/workbook.xml')
    out={}
    for s in wb.find('m:sheets',ns):
        name=s.get('name'); sp=wr[s.get('{%s}id'%ns['r'])]
        sr=rels(z,sp); res=[]
        sx=ET.fromstring(z.read(sp)); dr=sx.find('m:drawing',ns)
        if dr is not None:
            dp=sr[dr.get('{%s}id'%ns['r'])]; drl=rels(z,dp); dx=ET.fromstring(z.read(dp))
            for anc in dx:
                pic=anc.find('xdr:pic',ns)
                if pic is None: continue
                emb=pic.find('xdr:blipFill/a:blip',ns).get('{%s}embed'%ns['r'])
                fr=anc.find('xdr:from',ns); to=anc.find('xdr:to',ns)
                g=lambda e,t:int(e.find('xdr:'+t,ns).text)
                r0,c0=g(fr,'row')+1,g(fr,'col')+1
                r1,c1=(g(to,'row')+1,g(to,'col')+1) if to is not None else (r0,c0)
                ext=anc.find('xdr:ext',ns)
                res.append(dict(r0=r0,c0=c0,r1=r1,c1=c1,media=drl[emb]))
        out[name]=res
    return z,out
