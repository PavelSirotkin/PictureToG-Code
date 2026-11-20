const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=require('path');
const ctx={console,navigator:{userAgent:"node"}};ctx.self=ctx;vm.createContext(ctx);
for(const f of ['clipper.js','geometry.js','gcode.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../js',f),'utf8'),ctx);
const run=s=>vm.runInContext(s,ctx);const rect='[[0,0],[20,0],[20,20],[0,20],[0,0]]';
const one=run(`GCodeGenerator.chainsToGcode([${rect}],{toolDia:2,feedrate:100,finalDepth:3,safeZ:5,simplifyEps:0,numPasses:3,bridgeMode:true,bridgeSize:2,bridgeCount:2}).gcode`);
assert(one.includes('G1 Z-1.000 F100.0')&&one.includes('G1 Z-2.000 F100.0')&&one.includes('G1 Z-3.000 F100.0'));
assert.equal((one.match(/^G1 Z0.000$/gm)||[]).length,2);
const offset=run(`Geometry.offsetContours([${rect}, [[5,5],[15,5],[15,15],[5,15],[5,5]]],1)`);
let bounds=offset.map(p=>[Math.min(...p.map(x=>x[0])),Math.max(...p.map(x=>x[0]))]).sort((a,b)=>a[0]-b[0]);assert.deepEqual(JSON.parse(JSON.stringify(bounds)),[[1,19],[4,16]]);
assert.throws(()=>run(`Geometry.offsetContours([[[0,0],[1,0],[1,1],[0,1],[0,0]]],1)`),/исчез/);
let seg=run(`Geometry.insertBridges([[0,0],[5,0],[10,0],[15,0],[20,0]],2,2)`);assert.equal(seg.filter(s=>s.isBridge).length,2);
const center=run(`GCodeGenerator.chainsToGcode([[[0,0],[10,0]]],{toolDia:2,feedrate:100,finalDepth:3,safeZ:5,simplifyEps:0,numPasses:2,centerline:true,bridgeMode:true}).gcode`);assert(center.includes('G1 Z-1.500 F100.0'));assert(!center.includes('G1 Z0.000'));
assert.throws(()=>run(`Geometry.offsetContours([[[0,0],[10,0],[10,10],[0,10]]],1)`),/не замкнут/);
assert.throws(()=>run(`Geometry.insertBridges([[0,0],[2,0]],2,2)`),/слишком короткий/);
console.log('PASS multipass, bridges, nested offsets, rejected collapse, open centerline');


