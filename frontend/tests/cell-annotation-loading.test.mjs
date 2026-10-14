import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import { CellAnnotationEditor } from '../js/cell-annotation-editor.js';
const deferred = () => { let resolve, reject; const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject}; };
function editorFor(requests) {
    const editor=Object.create(CellAnnotationEditor.prototype);
    Object.assign(editor,{api:{getPatchCells:()=>requests.shift().promise},viewer:{annotations:[],requestRender(){}},onStatus(){},render(){},
        clearViewerAnnotations(){this.viewer.annotations=[];},syncViewer(){this.viewer.annotations=this.cells;this.viewerSynced=true;}});
    return editor;
}
for(const fails of [false,true])test(`older duplicate response cannot replace current cells (${fails?'failure':'success'})`,async()=>{
    const old=deferred(),latest=deferred();const editor=editorFor([old,latest]);
    const a=editor.open('slide',{patch_id:'patch_4'}),b=editor.open('slide',{patch_id:'patch_4'});
    latest.resolve({cells:[{id:'latest'}]});assert.equal(await b,true);
    if(fails)old.reject(new Error('late network failure'));else old.resolve({cells:[]});
    assert.equal(await a,false);assert.equal(editor.cells[0].id,'latest');assert.equal(editor.viewer.annotations[0].id,'latest');
});
test('leaving patch view during load retains cells without drawing in WSI',async()=>{
    const request=deferred(),editor=editorFor([request]);let focused=true;
    const loading=editor.open('slide',{patch_id:'patch_4'},{shouldSyncViewer:()=>focused});
    focused=false;request.resolve({cells:[{id:'saved'}]});await loading;
    assert.equal(editor.cells.length,1);assert.equal(editor.viewer.annotations.length,0);assert.equal(editor.viewerSynced,false);
});
const source=await readFile(new URL('../js/annotation.js',import.meta.url),'utf8');
const loader=source.slice(source.indexOf('async function _loadSavedAnnotationsForSlide('),source.indexOf('async function _downloadAnnotations('));
for(const kind of ['cell','tissue'])test(`late slide metadata response preserves ${kind} ownership`,async()=>{
    const request=deferred();const viewer={annotations:[{id:'initial'}],clearAnnotations(){this.annotations=[];}};
    const context=vm.createContext({ANNOTATION_PAGE_KIND:kind,currentSlideId:'slide',currentSlideMemo:'',currentSlideMemoHistory:[],viewer,
        api:{loadAnnotations:()=>request.promise},renderAnnotationPanel(){},_splitAnnotationPayload:p=>p,
        _setSlideListMemoIndicator(){},_syncSlideMemoButton(){},setStatus(){},console,
        _applyLoadedAnnotations:list=>{viewer.annotations=list;}});
    vm.runInContext(loader,context);
    const pending=context._loadSavedAnnotationsForSlide('slide');
    if(kind==='cell')assert.equal(viewer.annotations[0].id,'initial');
    viewer.annotations=[{id:'patch-cell'}];
    request.resolve({slideMemo:'memo',slideMemoHistory:[],annotations:[{id:'slide-roi'}]});await pending;
    assert.equal(viewer.annotations[0].id,kind==='cell'?'patch-cell':'slide-roi');assert.equal(context.currentSlideMemo,'memo');
});
