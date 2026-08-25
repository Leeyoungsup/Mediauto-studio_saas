# MeDIAuto Studio SaaS Page-by-Page User Guide

> Draft for the user manual<br>
> Screens captured: August 21, 2026<br>
> English button and menu labels are shown exactly as they appear in the application whenever possible.

Korean version: [PAGE_FEATURE_GUIDE.md](PAGE_FEATURE_GUIDE.md)

## Purpose of This Guide

This guide explains what users can do on each page rather than describing the system's internal architecture. New users can follow it from account sign-in through slide upload, AI analysis, annotation, review, and completion.

## Screenshot Notice

The screenshots in this guide are the de-identified versions prepared for public documentation. User names, login IDs, names, departments, access IP addresses and locations, and sample identifiers have been pixelated. The data shown and the availability of buttons may differ depending on the signed-in user's role and the current workflow state.

## Overall Workflow

1. Create an account and wait for administrator approval.
2. Create a working project from Home or Project.
3. Upload slides to the project.
4. Open the required AI, Tissue Annotation, or Cell Annotation workspace.
5. Select a slide and perform analysis or annotation.
6. Save the results and complete the Review and Termination stages.

## Access by Role

| Role | Main access |
| --- | --- |
| Admin | All features, project deletion, user approval and management, and system worker settings |
| Doctor | Project creation and editing, AI analysis, annotation class setup, annotation, review, and termination |
| Labeler | AI execution and assigned Tissue/Cell Annotation work; project management, review, and termination are restricted |
| Viewer | Primarily views projects, slides, and existing results |

Buttons may be hidden or disabled according to the user's role and the current workflow state.

---

## 1. Sign In and Sign Up

### Page URL

`/login`

### Sign In

![Sign-in page with Login ID and Password fields](../figure/manual-redacted/01-login/01-sign-in.png)

*Figure 1. Sign-in page*

1. Enter your `Login ID`.
2. Enter your `Password`.
3. Select `Sign in`.
4. For an MFA-enabled account, enter the six-digit authentication code in the field that appears, then submit the sign-in form again.
5. After successful authentication, the Home page opens.

### Create an Account

![Sign-up page with Name, Department, Login ID, and Password fields](../figure/manual-redacted/01-login/02-sign-up.png)

*Figure 2. Sign-up page*

1. Select `Sign up` at the bottom of the page.
2. Enter the following information:

   - `Name`: Required
   - `Department`: Optional
   - `Login ID`: The ID used to sign in
   - `Password`: The account password

3. Select `Sign up`.
4. Wait for an administrator to approve the request.
5. You can sign in after an administrator approves the account and assigns a role.

### Input Requirements

- A Login ID must contain 4–30 letters, numbers, or underscores.
- A password must be at least eight characters long.
- A password must contain at least one uppercase letter, one lowercase letter, one number, and one special character.

### If You Cannot Sign In

![Error displayed when a deactivated account attempts to sign in](../figure/manual-redacted/01-login/03-account-deactivated-error.png)

*Figure 3. Deactivated-account sign-in error*

- `Pending` or an approval-pending message: Administrator approval is required.
- Rejection message: Ask an administrator to check the registration status.
- Deactivated-account message: Ask an administrator to reactivate the account.
- Lock message: Too many failed sign-in attempts have locked the account. Wait for the lock period to expire or ask an administrator to unlock it.
- Invalid authentication code: Confirm that the authenticator device time is correct, then enter a newly generated code.

---

## 2. Common Top Navigation

After signing in, the following menus are available at the top of most pages.

| Menu | Description |
| --- | --- |
| Home | View storage usage, recent slides, and project status. |
| Project | Create projects and edit project settings. |
| Data Linkage | View slides from the same case together with clinical information. |
| AI | Open the AI analysis workspace. |
| Annotation → Tissue Annotation | Open the tissue-region annotation workspace. |
| Annotation → Cell Annotation | Open the patch-based cell annotation workspace. |
| Admin | Manage users and system workers. Available only to Admin users. |

### User Menu

- Select the user name in the top bar to open Profile.
- Select `Logout` to end the current session and return to the sign-in page.

---

## 3. Home Page

### Page URL

`/home`

### Purpose

Home is the first dashboard displayed after sign-in. It provides storage usage, recent work, project status, and shortcuts to frequently used features.

![Home dashboard showing storage, recent slides, quick actions, and project status](../figure/manual-redacted/02-home/01-dashboard.png)

*Figure 4. Home dashboard*

### Check Storage Usage

The storage area at the top of the page shows:

- Currently used storage
- Total available storage
- Percentage used

If the storage is nearly full, contact an administrator before uploading new slides.

### Reopen a Recent Slide

The `Recent Slides` area lists recently opened slides.

1. Find the required thumbnail or card.
2. Select the card.
3. The slide opens in the AI, Tissue Annotation, or Cell Annotation workspace most recently used for that slide.

Each card may show the file name, size, last activity time, and work status.

### Quick Actions

- `AI Viewer`: Opens the AI project selection page.
- `Upload`: Opens the slide upload window.
- `Profile`: Opens your account information.
- `Admin`: Opens the administrator page.

Upload or Admin may not be displayed for every role.

### Check Project Status

The project area provides:

- Project name and status
- Hospital or organization
- Owner
- Number of slides
- Charts by project and hospital
- Navigation to the full project list

Hover over a chart item to display its detailed count.

### Open a Project

1. Select `Open` for the project you want to use.
2. Choose a workspace in the dialog:

   - `AI`
   - `Tissue Annotation`
   - `Cell Annotation`

3. The slide list for the selected workspace opens.

### View or Edit Project Information

- Select `Info` or the Edit action.
- Review the title, hospital, department, owner, status, due date, and description.
- Admin and Doctor users can edit this information.

---

## 4. Project Page

### Page URL

`/project`

### Purpose

Use this page to create projects and manage project-specific work information and automatic AI settings. It resembles the Home dashboard but focuses on project administration.

![Project page showing the project list and status overview](../figure/manual-redacted/03-project/01-project-list.png)

*Figure 5. Project list*

### Create a Project

This feature is available to Admin and Doctor users.

![New-project page for entering project information and automatic AI settings](../figure/manual-redacted/03-project/04-create-project.png)

*Figure 6. Create a new project*

1. Select `New Project`.
2. Enter the project information:

   - `Title`: Project title
   - `Hospital`: Hospital or organization
   - `Department`: Department
   - `Owner`: Person responsible for the project
   - `Status`: Project status
   - `Due Date`: Due date
   - `Description`: Project description

3. Configure automatic AI tasks if required.
4. Select `Save` or the create button.

### Project Status

| Status | Recommended use |
| --- | --- |
| Active | Newly created and available for work |
| In Progress | Work is currently in progress |
| Review | Results are being reviewed |
| Done | Work has been completed |
| Archived | Project is retained for reference |

Use status values consistently according to your organization's operating procedure.

### Edit a Project

![Project settings page for editing information and automatic AI settings](../figure/manual-redacted/03-project/02-edit-project-settings.png)

*Figure 7. Edit project information and automatic AI settings*

1. Select `Info` or Edit in the project list.
2. Change the required fields.
3. Save the changes.

Labeler and Viewer users can view project information but cannot create or edit projects.

![Dialog for selecting AI, Tissue Annotation, or Cell Annotation from a project](../figure/manual-redacted/03-project/03-open-project-workspace.png)

*Figure 8. Select a project workspace*

### Automatic AI Settings

After slides are added, the system can run selected analyses automatically when processing resources are idle.

Available tasks include:

- Quanti HE: Stomach, Breast, Other
- Quanti PD-L1: Stomach CPS, Lung TPS
- Quanti IHC: HER2, ER/PR Allred, KI-67
- VS IHC: IHC → Virtual H&E

Select a Target Resolution for VS IHC.

| Setting | Approximate magnification | Characteristics |
| --- | --- | --- |
| 4.0 µm/px | ×2.5 | Fastest, coarser output |
| 2.0 µm/px | ×5 | General review |
| 1.0 µm/px | ×10 | More detailed output |
| 0.5 µm/px | ×20 | Most detailed; may require more processing time |

### Cell Annotation AI Assistance

You can select one model to assist patch labeling in Cell Annotation.

1. Enable Cell Annotation assistance.
2. Select a model appropriate for the slide stain and task.
3. Save the project.

Changing this setting may change the assistance results and class configuration generated later. Finalize the model before annotation begins.

### Delete a Project

- Only an Admin can delete a project.
- Only an empty project with no slides or child folders can be deleted.
- Verify the project name in the confirmation dialog.

---

## 5. Shared Project Selection for AI and Annotation

Opening AI, Tissue Annotation, or Cell Annotation from the top menu first displays the project selection page.

![AI project list with search and filters](../figure/manual-redacted/05-ai-viewer/01-project-list.png)

*Figure 9. Workspace project selection*

### Search for a Project

The search field checks the following content:

- Project name and title
- Owner
- Hospital
- Department
- Status
- Description

### Filters

- `Hospital`
- `Owner`
- `Status`
- `Rows`: 10, 30, or 50 projects per page

### Additional Conditions

Enable `Additional conditions` to use:

- `Has slides`: Only projects containing slides
- `Has folders`: Only projects containing child folders
- `Min slides`: Projects with at least the specified number of slides

### Sort the List

Select a column heading to sort it in ascending or descending order:

- Project
- Hospital
- Owner
- Slides
- AI Analyzed
- Folders
- Status

### Open a Project

Select the project row or `Open` to enter that workspace.

---

## 6. Upload Page

### Page URL

`/upload`

### Purpose

Use this page to select a project and folder and upload WSI files. It opens as a separate window from Home or a workspace.

![Slide Upload page for selecting a destination and adding WSI files](../figure/manual-redacted/04-upload/01-slide-upload.png)

*Figure 10. Slide Upload page*

### Select an Upload Destination

1. Select a destination from `Project`.
2. Select a child `Folder` if required.
3. When opened from a workspace, the current project and folder may already be selected.

A project selection is required.

### Add Files

Use any of these methods:

- Select the file area and choose files in the file browser.
- Drag and drop files into the upload area.
- Select multiple files at once.

### Supported Files

- SVS
- NDPI
- VMS, VMU
- SCN
- MRXS
- TIFF, TIF
- PNG
- JPG, JPEG
- Philips iSyntax, i2syntax

Because ordinary JPG/JPEG files do not contain objective-power or physical-resolution metadata, the system registers them with a fixed calibration of `20×` and `0.5 µm/px`. Magnification and distance measurements shown for JPG/JPEG files are calculated from this fixed value.

The default maximum size per file is 20 GB.

### Upload Progress

- Files are processed one at a time in list order.
- Progress is shown for each file.
- File registration and validation may continue after transfer completes.
- Do not close the window during upload.
- A warning is displayed if you try to close an active upload.
- If one file fails, the remaining files continue processing.

### If a File Already Exists

Choose an action for each conflicting file:

- `Overwrite`: Remove the existing file and related work data, then replace it with the new file.
- `Skip`: Keep the existing file and skip the incoming file.

Overwrite can affect existing AI results and annotations. Use it carefully.

### Upload Complete

Review the final counts:

- `Uploaded`: Successful files
- `Failed`: Failed files
- `Skipped`: Skipped files

Closing the upload window refreshes the slide list in the original workspace.

### If an Upload Fails

- Confirm that the extension is supported.
- Confirm that a project is selected.
- Check that the file is not damaged.
- Check available storage.
- Check the network connection.
- Philips files require Philips support to be configured on the server.

---

## 7. Shared Slide List for AI, Tissue, and Cell Workspaces

![Slide list showing folders and slides in table form](../figure/manual-redacted/05-ai-viewer/02-slide-list-view.png)

*Figure 11. Slide List View*

### Navigate Folders

- Select a project or folder name in the breadcrumb to move to a parent location.
- Double-click or select a folder to open it.
- Users with permission can create, rename, and delete folders.

### Search for a Slide

Enter part of a file name in the search field to filter slides in the current folder.

![Slide list filtered by a file-name search](../figure/manual-redacted/05-ai-viewer/04-search-slides.png)

*Figure 12. Slide-name search results*

### List and Grid Views

- List View: Shows file names and statuses in a table.
- Grid View: Shows larger thumbnail cards.

![Slides displayed as large thumbnail cards in Grid View](../figure/manual-redacted/05-ai-viewer/03-slide-thumbnail-view.png)

*Figure 13. Slide Grid View*

![Viewer with the left slide panel collapsed](../figure/manual-redacted/05-ai-viewer/05-collapsed-slide-panel.png)

*Figure 14. Collapsed slide panel*

### Select Multiple Slides

| Input | Result |
| --- | --- |
| Ctrl/Cmd+click | Add or remove an item from the selection |
| Shift+click | Select a range from the last selected item |
| Drag in empty space | Select all items inside the rectangular selection area |

### Move Files

1. Select one or more slides.
2. Drag the selection to a destination folder or breadcrumb location.
3. Confirm the new location.

Because file paths can be associated with existing results and annotations, avoid moving slides while work is in progress.

### Thumbnail Size

Place the pointer over the left slide list and use `Ctrl+mouse wheel` to resize thumbnails.

### Context Menu

Right-click a slide or folder to display actions available for the current role and item. Before deleting anything, verify the file name and number of selected items.

---

## 8. Common WSI Viewer Controls

AI, Tissue Annotation, and Cell Annotation use the same basic WSI navigation controls.

### Pan and Zoom

| Input | Action |
| --- | --- |
| Left-button drag | Pan the slide |
| Middle-button drag | Pan the slide |
| Mouse wheel | Zoom around the center of the view |
| One-finger drag | Pan on a touch screen |
| Two-finger pinch | Zoom on a touch screen |
| `Fit` | Fit the entire slide in the Viewer |
| `Zoom In`, `Zoom Out` | Zoom one step at a time |

![WSI Viewer tools and keyboard shortcut help](../figure/manual-redacted/05-ai-viewer/09-shortcuts.png)

*Figure 15. Viewer tools and shortcut help*

### Minimap

- The minimap shows the current viewing area as a rectangle.
- Select a minimap position to move there.
- Drag the current-area rectangle to move quickly.
- Resize or collapse the minimap as needed.

### Left and Right Panels

- Drag a panel boundary to resize the panel.
- Collapse a panel to enlarge the Viewer.
- When a collapsed boundary has focus, press Enter or Space to reopen it.
- On smaller screens, panels may be displayed as drawers.

### Slide Information

`Slide Info` provides:

![Slide Info dialog showing the file name, scanner, magnification, MPP, and clinical information](../figure/manual-redacted/05-ai-viewer/06-slide-information.png)

*Figure 16. Slide Info*

- File name
- Scanner/Vendor
- Magnification
- Pixel size
- MPP
- Physical dimensions
- Clinical information

Clinical information may be saved automatically when the dialog is closed after editing.

### Hamamatsu Color

An NDP color-correction option may be available for Hamamatsu slides. Compare the original and corrected views and use the view defined by your organization's procedure.

### Same Case

Use Same Case to find slides from the same patient or sample with different markers.

![Same Case dialog for finding and selecting slides with other markers](../figure/manual-redacted/05-ai-viewer/07-same-case-slides.png)

*Figure 17. Same Case slide selection*

1. Select `Same Case`.
2. Review the slide thumbnails and AI-result indicators.
3. Select up to four slides.
4. Select a single view to open only one slide.
5. Select Multi View to compare several slides.

### Multi View

![Several marker slides displayed together in Multi View](../figure/manual-redacted/05-ai-viewer/08-multi-view.png)

*Figure 18. Basic Multi View*

- Display two to four slides at the same time.
- Use `Fit` independently in each pane.
- Select a pane to make that slide active.
- AI, Annotation, and Info actions apply to the active slide.
- Exit Multi View to return to the original single-slide view.

![Virtual Stain and several marker AI results compared in Multi View](../figure/manual-redacted/05-ai-viewer/10-analysis-result-multi-view.png)

*Figure 19. Same Case AI results in Multi View*

---

## 9. AI Page

### Page URL

`/ai`

### Purpose

Run AI analysis on an entire slide or selected ROI, then review result cells, scores, and visualizations.

### Start an Analysis

1. Open AI.
2. Select a project.
3. Open a slide from the left list.
4. Draw an ROI if required.
5. Select an analysis type in the right AI panel.
6. Select the analysis button.
7. Wait until progress reaches completion.

### ROI Tools

![Polygon and Rectangle ROIs defining the AI analysis area](../figure/manual-redacted/06-ai-analysis/01-analysis-region.png)

*Figure 20. Define an AI analysis ROI*

| Tool | Use |
| --- | --- |
| Polygon | Drag around the required boundary. |
| Polygon Brush | Paint a free-form region. |
| Rectangle | Drag from the first corner to the opposite corner. |
| 1 mm² Rectangle | Place a fixed-area rectangle. |
| 1 mm² Circle | Place a fixed-area circle. |
| Ruler | Connect two points to measure physical distance. |

When a visible Polygon or Rectangle ROI exists, only that region is analyzed. With no ROI, the entire slide is analyzed.

### Edit an ROI

- Select the ROI.
- Drag a vertex or rectangle corner to reshape it.
- Use `Shift+drag` to move the entire ROI.
- Use `Alt+click` on a polygon edge to add a vertex.
- Use `Ctrl+click` on overlapping polygons of the same class to merge them.
- Press `Delete` to remove the selected ROI.
- Press `Esc` or right-click to exit drawing mode.

### VirtualStain

VirtualStain generates a Virtual H&E image from an IHC source slide.

![IHC and generated Virtual H&E compared in Split View](../figure/manual-redacted/06-ai-analysis/07-virtual-stain-split-view.png)

*Figure 21. Virtual Stain Split View*

1. Select `VirtualStain`.
2. Select Target Resolution.
3. Run the task.
4. After completion, enable `Overlay` to place the result over the source.
5. Enable `Split View` to compare IHC on the left with Virtual H&E on the right.
6. Drag the center divider to change the comparison ratio.

A lower MPP value provides more detail but may require more time and processing resources.

### Quanti HE

Quanti HE detects and classifies cells in an H&E slide.

![Detected H&E cells and class counts](../figure/manual-redacted/06-ai-analysis/08-quanti-he-results.png)

*Figure 22. Quanti HE results*

![Spatial heatmap of Quanti HE cell distribution](../figure/manual-redacted/06-ai-analysis/09-quanti-he-spatial-heatmap.png)

*Figure 23. Quanti HE Spatial Heatmap*

1. Under `Quanti`, select `HE`.
2. Select `Breast`, `Stomach`, or `Other` as appropriate.
3. Run the analysis.
4. Review the cell count for each class.

Common classes include:

- Neutrophil
- Epithelial
- Lymphocyte
- Plasma
- Eosinophil
- Stromal cell
- Tumor Epithelial
- Benign Epithelial

Breast and Stomach additionally separate epithelial cells into Tumor and Benign classes.

### Quanti PD-L1

![PD-L1 result cells and score](../figure/manual-redacted/06-ai-analysis/15-quanti-pdl1-results.png)

*Figure 24. Quanti PD-L1 results*

![CPS and TPS calculations in a PD-L1 analysis](../figure/manual-redacted/06-ai-analysis/16-quanti-pdl1-cps-tps-analysis.png)

*Figure 25. PD-L1 CPS and TPS results*

1. Under `Quanti`, select `PD-L1`.
2. Select the tissue:

   - `Stomach`: CPS
   - `Lung`: TPS

3. Run the analysis.
4. Review the result-cell counts and calculated score.

Stomach CPS compares positive tumor and immune cells with viable tumor cells. Lung TPS compares positive tumor cells with all tumor cells. Cells classified as Other or Non-Tumor are hidden by default and excluded from the score.

### Quanti IHC

#### HER2

![HER2 0+, 1+, 2+, and 3+ cells with analysis scores](../figure/manual-redacted/06-ai-analysis/11-quanti-ihc-her2-results.png)

*Figure 26. Quanti IHC HER2 results*

![Editing the class of one selected HER2 result cell](../figure/manual-redacted/06-ai-analysis/12-quanti-ihc-her2-single-cell-edit.png)

*Figure 27. Edit one HER2 result cell*

![Batch-editing the classes of selected HER2 result cells](../figure/manual-redacted/06-ai-analysis/13-quanti-ihc-her2-batch-cell-edit.png)

*Figure 28. Edit multiple HER2 result cells*

Review:

- Counts of 0+, 1+, 2+, and 3+ cells
- Most frequent grade
- Weighted average score across all cells

#### ER/PR

![ER or PR result cells and Allred score](../figure/manual-redacted/06-ai-analysis/10-quanti-ihc-erpr-results.png)

*Figure 29. Quanti IHC ER/PR results*

![Proportion, intensity, and Allred result visualization](../figure/manual-redacted/06-ai-analysis/04-result-allred-analysis.png)

*Figure 30. Allred analysis visualization*

Review:

- Proportion Score
- Intensity Score
- Allred Total Score, the sum of the two values
- Positive or Negative result

#### KI-67

![KI-67 positive and negative cells with the labeling index](../figure/manual-redacted/06-ai-analysis/14-quanti-ihc-ki67-results.png)

*Figure 31. Quanti IHC KI-67 results*

Review:

- Positive cell count
- Negative cell count
- Positive / Total ratio
- High or Low classification using the 14% threshold

### Monitor or Cancel Analysis

- Progress and current state are displayed while analysis runs.
- Selecting the run button again may ask whether to cancel or send a cancellation request.
- Large slides may take time to display results.
- Status badges in the left list also show running and completed states.

### Manage Result Display

![AI cell density displayed as a heatmap](../figure/manual-redacted/06-ai-analysis/02-result-heatmap.png)

*Figure 32. AI result Heatmap*

- Use the visibility control beside a class name to hide or show that class.
- Use the all-visible control to hide or show all classes.
- Hidden classes can affect visual review and score interpretation. Confirm which classes are hidden.
- Use Heatmap to turn the density display on or off.

### Edit Result Cells

Cell editing is available to Admin and Doctor users.

| Input | Action |
| --- | --- |
| Alt+left-click | Select a nearby result cell and change its class |
| Alt+left-drag | Free-form selection of multiple visible cells |
| Alt+right-click | Add a result cell at the selected position |
| Alt+right-drag | Select multiple hidden Other cells and assign a visible class |
| Alt+A | Select a Sticky Class for repeated edits |
| 1–9, 0 | Select class 1–10 in the open editor |
| Delete or D | Delete selected cells |
| Ctrl+Z | Undo the previous edit |
| Ctrl+Y or Ctrl+Shift+Z | Redo an undone edit |

CPS, TPS, HER2, Allred, and KI-67 values are recalculated immediately after cell edits.

### Save Results

- `Save Results`: Save the current edits as your user result set.
- `Load Results`: Load the original AI result or a saved user result set.
- You can delete your own saved result sets.
- `Clear Results`: Clear the results currently displayed.

Clearing the display or deleting a user result set does not delete the original AI result. Labelers can run AI but have restricted cell editing and Save/Load access. Viewers cannot run AI.

### Visualize

Use `Visualize` to review graphical result summaries.

![Class distribution charts in Visualize](../figure/manual-redacted/06-ai-analysis/03-result-class-distribution.png)

*Figure 33. Class distribution visualization*

![Confidence distribution of AI result cells](../figure/manual-redacted/06-ai-analysis/05-result-confidence-distribution.png)

*Figure 34. Confidence distribution visualization*

Available views include:

- Class-distribution bar chart
- Class-distribution pie chart
- Model-specific results
- Spatial Heatmap
- Segmentation Map
- Confidence distribution

### Export a PDF

![AI analysis report prepared for PDF export](../figure/manual-redacted/06-ai-analysis/06-pdf-analysis-report.png)

*Figure 35. AI analysis PDF report*

1. Select PDF Export in Visualize.
2. If the browser supports destination selection, choose the location and file name.
3. Otherwise, the file is saved to the browser's default download folder.

If PDF export does not work on a closed network, contact an administrator.

---

## 10. Tissue Annotation Page

### Page URL

`/annotation` or `/tissue-annotation`

### Purpose

Mark tissue regions by class and manage their annotation, review, and termination states.

![Tissue Annotation Viewer with class-based regions and workflow controls](../figure/manual-redacted/07-tissue-annotation/01-annotation-viewer.png)

*Figure 36. Tissue Annotation workspace*

### Start Annotation

1. Open Tissue Annotation.
2. Select a project.
3. Open a slide from the left list.
4. Select a class on the right.
5. Select a drawing tool at the top.
6. Draw a region in the Viewer.
7. Confirm its memo and class.
8. Select `Save` or press `Ctrl+S`.

Previously saved annotations load automatically when a slide opens.

### Drawing Tools

| Tool | Description |
| --- | --- |
| Polygon | Creates a closed region from the dragged path. |
| Polygon Brush | Paints a free-form region. |
| Rectangle | Creates a rectangular region. |
| Point | Places a point annotation. |
| Cut | Reshapes a selected polygon using a new path. |
| 1 mm² Rectangle | Creates a rectangle with a physical area of 1 mm². |
| 1 mm² Circle | Creates a circle with a physical area of 1 mm². |
| Ruler | Measures physical distance between two points. |

The Ruler automatically straightens lines that are almost horizontal or vertical.

### Manage Classes

Admin and Doctor users can manage project-specific classes.

![Tissue Annotation class names, colors, and order settings](../figure/manual-redacted/07-tissue-annotation/02-class-management.png)

*Figure 37. Tissue Annotation class management*

Available actions include adding, renaming, recoloring, reordering, deleting, hiding, and showing classes. At least one class must remain. Deleting a class already in use may move existing annotations to another default class, so avoid changing the class structure after work begins.

### Assign a Class

For a new annotation:

1. Select a class on the right.
2. Draw the annotation.

For an existing annotation:

1. Select the annotation.
2. Select the required class.
3. Use Apply or press its number key.

Keys `1–9` and `0` represent classes 1–10 in list order.

### Annotation List

- Select an ID to select the annotation.
- Double-click an ID to center that annotation in the Viewer.
- Use the visibility control to hide or show it.
- Use the Memo area or right-click the row to open its memo.
- Use Delete to remove it.

### Reshape an Annotation

- Drag a vertex of the selected annotation.
- Drag a rectangle corner to resize it.
- Use `Shift+drag` to move the entire annotation.
- Hold `Alt` over a polygon edge to preview a new vertex, then `Alt+click` to add it.
- Hold `Ctrl` over overlapping polygons of the same class, then `Ctrl+click` to merge them.

### Display Style

- `Line`: 1–12 px
- `Fill`: 0–80%

Style settings may also apply to other annotation pages for the current account.

### Slide Memo

- Open it from the Memo toolbar button or with `Ctrl+M`.
- Create, edit, or delete the current memo.
- Review memo history.
- Reply to and accept an earlier memo.
- A slide with a memo shows an `M` indicator in the list.

### Annotation Memo

- Select the Memo area in an annotation row or right-click the row.
- Manage the memo and its history.
- The memo is linked only to the selected annotation.

### Save

- Use `Save` or `Ctrl+S`.
- Current geometry, class assignments, and memos are saved.
- Confirm the saved state before changing slides.
- `Clear All` removes all annotations currently shown; use it carefully.

### Workflow

| Stage | Meaning |
| --- | --- |
| Annotation | Create annotations |
| Review | Review completed annotation work |
| Termination | Final completion stage |

Colors and icons distinguish stages that can be started, Running, Done, Pending, and Rejected. Follow your organization's process, normally Annotation → Review → Termination. Labelers usually complete Annotation, while Doctors or Admins perform Review and Termination.

### Virtual H&E Reference

The AI panel in Tissue Annotation can provide VS IHC features:

- Generate Virtual H&E
- Overlay
- IHC | Virtual H&E Split View

Use these views to compare the source and generated image while annotating.

### Main Shortcuts

| Input | Action |
| --- | --- |
| Ctrl/Cmd+S | Save current annotations |
| Ctrl/Cmd+M | Open Slide Memo |
| Ctrl/Cmd+Z | Undo |
| Ctrl/Cmd+Y | Redo |
| Ctrl/Cmd+Shift+Z | Redo |
| 1–9, 0 | Change the selected annotation's class |
| Delete | Delete the selected annotation |
| Esc | Exit drawing mode or close shortcut help |
| Alt+wheel | Change Brush size |
| Shift+drag | Move the selected annotation |
| Ctrl+drag | Pan while over an annotation |

---

## 11. Cell Annotation Page

### Page URL

`/cell-annotation`

### Purpose

Define WSI regions to label, then annotate cells with bounding boxes and classes inside fixed-size patches. Each patch follows Annotation, Review, and Termination stages.

### Overall Procedure

1. Select a project and slide.
2. Draw Required regions and any Exclude regions in WSI View.
3. Apply the regions to create work patches.
4. Select a patch and enter Patch View.
5. Change Annotation to Running.
6. Review AI assistance or mark cells manually.
7. Correct cell classes and positions.
8. Save, then change Annotation to Done.
9. A Doctor or Admin performs Review.
10. Correct rejected patches and complete Termination for accepted patches.

### Project Class Settings

Open class settings from the project selection page.

![Project-level cell class settings for Cell Annotation](../figure/manual-redacted/08-cell-annotation/01-annotation-settings.png)

*Figure 38. Cell Annotation project class settings*

- Review the classes used by the project.
- Admin and Doctor users can add, edit, and reorder classes.
- Renaming, recoloring, or deleting AI-required classes and Other may be restricted.
- User-defined classes are maintained separately.

Finalize the class structure before work begins. Large changes after annotation starts can make existing patches inconsistent.

### Create a Required Region in WSI View

Required marks tissue that must be labeled.

1. Select Required mode.
2. Draw a polygon around the target tissue.
3. Review the green region and proposed patches.
4. Select `Apply` after defining all required regions.

Before Apply, use `Ctrl+Z` to undo the last region definition.

### Create an Exclude Region

Exclude removes tissue from the work area.

1. Select Exclude mode.
2. Draw a polygon around the area to omit.
3. Review the red region and patches that will be excluded.
4. Select `Apply`.

Apply adds patches intersecting Required and excludes patches intersecting Exclude. It applies the current changes incrementally rather than rebuilding every patch.

### Clear All Patches

Only Admin and Doctor users can do this.

- All patch states and cell labels are removed.
- Related patch images and work information are affected.
- A five-second countdown is displayed.
- Cancel before the countdown ends if the action was selected accidentally.

### Patch List

![Patch list showing Annotation, Review, and Termination states](../figure/manual-redacted/08-cell-annotation/02-patch-list.png)

*Figure 39. Cell Annotation patch list*

| Column | Content |
| --- | --- |
| Patch | Patch number in `patch_N` format |
| Annotation | Annotation state |
| Review | Review state |
| Termination | Termination state |
| Memo | Whether a memo exists |

- Select a column heading to sort.
- Select a row, or focus it and press Enter or Space.
- Double-click a row to open Patch View.
- Right-click a row to open Memo or patch-removal actions.

### Open or Close Patch View

- Double-click the selected patch, or press `P`.
- Press `P` again to return to WSI View.
- The previous WSI position and zoom are restored.
- Select `Fit Patch` to fit the patch to the Viewer.

### Start Patch Work

A new Required patch must be changed to Annotation Running before editing.

1. Check the Annotation state in Patch View.
2. Change it to `Running`.
3. Add or edit cells.
4. Save the work.
5. Change Annotation to `Done`.

Current cell labels are saved before the state changes to Done.

### Draw a Cell Manually

- Select Rectangle.
- Drag around the cell.
- The currently selected class is assigned.
- The saved geometry is a bounding box.

### BBox and Point Views

- `BBox`: Shows the complete cell rectangle.
- `Point`: Shows a compact center point.

![Cell labels shown as bounding boxes](../figure/manual-redacted/08-cell-annotation/03-bounding-box-display.png)

*Figure 40. Cell BBox display*

![Cell labels shown as center points](../figure/manual-redacted/08-cell-annotation/04-point-display.png)

*Figure 41. Cell Point display*

Changing the display mode does not change the saved bounding-box data.

### Select Cells

- Select a cell for a single selection.
- Use list checkboxes to select multiple cells.
- Use `Alt+click` to add or remove a cell from the selection.
- Use `Alt+drag` for free-form multi-selection.
- Use the master checkbox to select all cells in the current list.
- Press `Esc` to clear a multi-selection.

### Change Cell Class

1. Select one or more cells.
2. Select the required class.

Alternatively, press `1–9` or `0` for classes 1–10.

### Delete Cells

Select cells and press `Delete`, `Backspace`, or `D`. All selected cells are deleted.

### Show or Hide Classes

| Input | Action |
| --- | --- |
| Ctrl/Cmd+1–9, 0 | Show or hide the corresponding class |
| Ctrl/Cmd+` | Show or hide all classes |

Hiding a class does not delete its labels.

### Use AI Assistance

If assistance is configured for the project:

1. Create the required WSI regions and patches.
2. Start assistance.
3. Wait for completion.
4. Open an empty Required patch.
5. Review the automatically loaded cell labels.
6. Correct wrong classes, positions, and missing cells.
7. Save and change Annotation to Done.

Assistance does not automatically overwrite a patch containing manual labels. AI output is a starting point and must be reviewed by a person.

### Patch Workflow

#### Annotation

- `Required`: Work is required.
- `Running`: Annotation is in progress.
- `Done`: Annotation is complete.

#### Review

- `Pending`: Not yet reviewed.
- `Done`: Review is complete.
- `Rejected`: Correction is required.

#### Termination

- `Pending`: Awaiting termination.
- `Current`: Termination is in progress.
- `Done`: Termination is complete.

A patch with Review Rejected can be edited again in Annotation.

### Labeler Permissions

A Labeler can edit cells when Annotation is Running or Review is Rejected. A Labeler cannot define WSI Required/Exclude regions, remove patches, change Review or Termination states, or change Patch Memos.

### Patch Memo

- Right-click a patch row or select its Memo item.
- Review the current memo and history.
- Manage replies and acceptance.
- Memo changes are restricted for Labelers.

### Check Project Progress

- Review Annotation, Review, and Termination completion rates in the slide list.
- Rejected patches use a separate color.
- Compare terminated patches with total patches at the top of the project.

### Main Shortcuts

| Input | Action |
| --- | --- |
| P | Switch between WSI View and Patch View |
| Ctrl/Cmd+S | Save the current patch |
| Ctrl/Cmd+Z | Undo region or cell edits |
| Ctrl/Cmd+Y | Redo |
| Ctrl/Cmd+Shift+Z | Redo |
| 1–9, 0 | Assign a class to selected cells |
| Ctrl/Cmd+1–9, 0 | Show or hide a class |
| Ctrl/Cmd+` | Show or hide all classes |
| Delete/Backspace/D | Delete selected cells |
| Alt+click | Add or remove a cell from the selection |
| Alt+drag | Free-form selection of multiple cells |
| Esc | Cancel selection or drawing |
| Enter/Space on a patch row | Select the patch |
| Double-click a patch row | Open Patch View |
| Right-click a patch row | Open the patch menu |

---

## 12. Data Linkage Page

### Page URL

`/data-linkage`

### Purpose

View slides belonging to the same case and enter clinical information shared by the case.

![Data Linkage page showing related slides and clinical information](../figure/manual-redacted/09-data-linkage/01-case-clinical-information.png)

*Figure 42. Data Linkage case and clinical information*

### Search for a Case

1. Select Project if needed.
2. Select Hospital if needed.
3. Enter a term in `Sample No`.
4. Select `Search` or press Enter.
5. Select 15, 30, or 50 rows per page.

### Sort the List

Select a heading to sort by Case ID, availability of Clinical Information, or Last Activity. Select it again to reverse the order.

### Select a Case

The right side shows:

- Year
- Sample ID
- Thumbnails of linked slides
- Currently selected slide
- Clinical information fields

### Review Linked Slides

- Select a thumbnail to change the preview.
- Use the mouse wheel to zoom around the pointer.
- Drag the preview to pan.
- Use `+` and `-` to zoom.
- Use the `H` button to reset the view.
- Use the `[]` button to fit the slide.

`H` and `[]` are on-screen buttons, not keyboard shortcuts.

### Enter Clinical Information

- ER proportion score
- ER intensity score
- PR proportion score
- PR intensity score
- Ki67 index
- PD-L1 CPS score
- ISH for HER2
- IHC for C-erbB2

If a value is unavailable or not applicable, use `na` according to your organization's data-entry rule.

### Save

1. Enter or edit values.
2. Confirm the `Not saved` indicator.
3. Select `Save`.
4. Confirm completion before opening another case.

The page warns you if you try to leave with unsaved changes.

### Important Notes

- Clinical information can be shared across the case rather than stored independently per slide.
- A change may appear on other linked marker slides.
- Follow the project's or organization's required score format.

---

## 13. Profile Page

### Page URL

`/profile`

![Profile page for editing account information and changing a password](../figure/manual-redacted/10-profile/01-account-and-password.png)

*Figure 43. Profile account and password settings*

### Edit Your Information

1. Select your user name in the top bar.
2. Review the current values in `My Profile`.
3. Edit `Name` and `Department`.
4. Select `Save Profile`.

You cannot directly change `Login ID` or `Role`. Ask an administrator if a change is required.

### Change Your Password

1. Enter the current password in `Current Password`.
2. Enter a new password in `New Password`.
3. Enter it again in `Confirm New Password`.
4. Select `Change Password`.
5. Sign in again after completion.

The new password must also be at least eight characters and include uppercase and lowercase letters, a number, and a special character. Other active devices or browsers may also require sign-in again.

---

## 14. Admin Page

### Page URL

`/admin`

Only an Admin can use this page.

### Pending: Approve Registration

![Pending registration page for assigning a role and approving or rejecting an account](../figure/manual-redacted/11-admin/01-pending-approvals.png)

*Figure 44. Admin Pending approval*

1. Open `Pending`.
2. Review the applicant's name, Login ID, and department.
3. Select Viewer, Labeler, Doctor, or Admin.
4. Select `Approve`.

To deny registration, select `Reject` and enter a reason if required. Assign the minimum role needed for the user's work.

### Users: Manage Accounts

![Users page with search, role, status, and account management actions](../figure/manual-redacted/11-admin/02-user-management.png)

*Figure 45. Admin user management*

Available actions include:

- Filter by status.
- Search by name or Login ID.
- Edit a user's name and department.
- Set a new password when needed.
- Change a role.
- Activate or deactivate an account.
- Unlock a locked account.
- Delete a user.
- Move between list pages.

Some high-risk actions are restricted for your own account or the last Admin account.

### Create: Create an Account Directly

![Admin page for creating a user with an initial password and role](../figure/manual-redacted/11-admin/03-create-user.png)

*Figure 46. Admin user creation*

1. Open `Create`.
2. Enter Login ID, Name, and Department.
3. Set an initial Password.
4. Select a Role.
5. Create the account.

An administrator-created account can be used immediately. Deliver the initial password securely and instruct the user to change it after the first sign-in.

### Activity: Review Sign-In and Work Records

![Activity page showing user sign-in times, IP addresses, and locations](../figure/manual-redacted/11-admin/04-login-activity.png)

*Figure 47. Admin sign-in activity records*

Review user activity, date and time, IP address and location, device information, and per-user detail. The detail page provides All, Login, Slides, AI, Projects, and Files categories. Change the date range and page to locate the required records.

### Settings: Manage Background Workers

![Settings page for AI Worker and Tile Worker Enabled and Running states](../figure/manual-redacted/11-admin/05-system-settings.png)

*Figure 48. Admin background worker settings*

#### AI Worker

Enables or disables automatic AI tasks configured for projects or folders.

#### Tile Worker

Enables or disables preparation of Viewer tiles for uploaded slides.

Each card distinguishes:

- `Enabled`: Whether the worker is configured for use
- `Running`: Whether the worker process is currently operating

After a change, confirm that the state refreshes. During normal operation, keep both workers enabled unless there is a specific maintenance reason not to.

---

## 15. Shortcut Quick Reference

On macOS, use `Cmd` for most shortcuts shown with `Ctrl`.

### Viewer and Annotation

| Input | Action |
| --- | --- |
| Mouse wheel | Zoom the WSI |
| Left-click or middle-button drag | Pan the view |
| Ctrl+drag | Pan while over an annotation or while drawing |
| Ctrl+click | Select an annotation even in drawing mode |
| Shift+drag | Move the selected annotation |
| Delete | Delete the selected annotation |
| Esc | Cancel drawing, selection, or a popup |
| Ctrl+Z | Undo |
| Ctrl+Y | Redo |
| Ctrl+Shift+Z | Redo |
| Alt+wheel | Change Polygon Brush size |
| Alt+click a polygon edge | Add a vertex |
| Ctrl+click overlapping same-class polygons | Merge polygons |

### Tissue Annotation

| Input | Action |
| --- | --- |
| Ctrl+S | Save annotations |
| Ctrl+M | Open Slide Memo |
| 1–9, 0 | Assign a class to the selected annotation |

### AI Result Editing

| Input | Action |
| --- | --- |
| Alt+left-click | Edit a result cell |
| Alt+left-drag | Select multiple visible cells |
| Alt+right-click | Add a cell |
| Alt+right-drag | Select multiple hidden Other cells |
| Alt+A | Select Sticky Class |
| 1–9, 0 | Assign a class in the editor |
| Delete/D | Delete result cells |

### Cell Annotation

| Input | Action |
| --- | --- |
| P | Switch between WSI and Patch View |
| Ctrl+S | Save the patch |
| 1–9, 0 | Assign a class to selected cells |
| Ctrl+1–9, 0 | Show or hide a class |
| Ctrl+` | Show or hide all classes |
| Delete/Backspace/D | Delete selected cells |
| Alt+click | Add or remove a cell from the selection |
| Alt+drag | Select multiple cells |

### Slide and Patch Lists

| Input | Action |
| --- | --- |
| Ctrl/Cmd+click | Select multiple slides |
| Shift+click | Select a slide range |
| Drag in empty space | Rectangular multi-selection |
| Ctrl+wheel | Change slide thumbnail size |
| Enter/Space on a patch row | Select the patch |
| Double-click a patch row | Open Patch View |

---

## 16. Pre-Work Checklists

### Before AI Analysis

- Confirm that the correct project and slide are open.
- Select the model and variant appropriate for the tissue.
- For ROI analysis, confirm that only the required ROIs are visible.
- If an earlier result must be retained, confirm its saved state before running a new analysis.

### Before Saving Tissue Annotation

- Confirm that every annotation has the correct class.
- Check for hidden classes or annotations.
- Distinguish Slide Memo from Annotation Memo.
- Save before changing a workflow state.

### Before Completing Cell Annotation

- Confirm that a person reviewed all AI assistance output.
- Check for missing cells and incorrect classes.
- Check whether any classes are hidden.
- Confirm that the current patch is saved before setting Annotation to Done.
- Review and address the reason or Memo for a Rejected review.

### Before Deleting or Overwriting a File

- Recheck the selected project, folder, and file name.
- Overwrite and Delete can affect existing AI results and annotations.
- Export or separately retain any results that must be preserved.

---

## 17. Common Situations

### An AI Button Is Disabled

- Check whether the account has the Viewer role.
- Confirm that the slide opened correctly.
- Check whether another AI task is running.
- Check the project configuration or ask an administrator to review the system state.

### An Annotation Cannot Be Edited

- A Viewer cannot edit annotations.
- A Cell Annotation Labeler can edit only when Annotation is Running or Review is Rejected.
- Confirm that the correct Patch View is open.

### The Slide Does Not Look Sharp

- A lower-resolution image may be displayed temporarily while tiles load.
- Wait for loading to finish.
- Select Fit, then zoom in again.
- If the issue continues, refresh the page or contact an administrator.

### Same Case Slides Are Not Found

- Confirm that file names follow your organization's case naming convention.
- Confirm that the files are registered correctly in their projects.
- Check that the case portion of each file name matches.

### A Slide Is Missing After Upload

- Confirm that the final upload status is `Uploaded`.
- Confirm that the correct project and folder are open.
- Refresh the list.
- Check whether a file-validation failure was reported.

### A PDF Is Not Saved

- Check whether the browser blocked the download.
- Check whether a save-location dialog opened behind another window.
- On a closed network, ask an administrator to review the PDF configuration.
