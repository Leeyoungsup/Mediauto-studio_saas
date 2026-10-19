import { test } from 'node:test';
import assert from 'node:assert/strict';
import { CellPatchWorkflow } from '../js/cell-patch-workflow.js';

for (const enterWhileLoading of [true, false]) {
    test(`late cell response ${enterWhileLoading ? 'syncs active patch view' : 'keeps WSI view clear'}`, async () => {
        let resolve;
        const response = new Promise(r => { resolve = r; });
        const workflow = Object.create(CellPatchWorkflow.prototype);
        Object.assign(workflow, {
            slideId:'slide', patchFocusActive:false, viewer:{annotations:[],setViewBounds(){}},
            focusLayer:{setPatch(){}}, _fitPatchView(){}, renderPatchList(){},
            _scrollSelectedPatchIntoView(){}, _syncAnnotationStatusPanel(){},
            _syncToolbarToggle(){}, _notifyPatchViewStateChange(){},
            editor:{
                cells:[],viewerSynced:false,clearViewerAnnotations(){},
                async open(slide,patch,options) {
                    await response;
                    if (!options.isCurrent()) return false;
                    this.cells=[{id:'saved-cell'}];
                    if(options.syncViewer)this.syncViewer();
                    else this.viewerSynced=false;
                    return true;
                },
                syncViewer(){workflow.viewer.annotations=this.cells;this.viewerSynced=true;},
            },
        });
        const loading=workflow.openPatch({patch_id:'patch_4',x:0,y:0,w:100,h:100});
        workflow.patchFocusActive=enterWhileLoading;
        resolve();await loading;
        assert.equal(workflow.editor.cells.length,1);
        assert.equal(workflow.viewer.annotations.length,enterWhileLoading?1:0);
        assert.equal(workflow.editor.viewerSynced,enterWhileLoading);
    });
}
