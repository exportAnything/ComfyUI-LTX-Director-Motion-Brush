It's 4am when i made this so there are probably tons of typos and it looks sloppy, sorry

1. You can now add videos to the "Main" track. Videos can be extended, trimmed, split, and they work with all of the other segments (You can do a quick test of this by uploading a video, and adding a text segment after it to control what happens next)
<img width="1012" height="752" alt="image" src="https://github.com/user-attachments/assets/3894687e-9e3a-45ad-9041-6ef3c6dddd41" />


2. You can now "inpaint" audio, or have audio generated between gaps of imported audio clips. You can toggle this on or off with the Inpaint toggle on the side bar
<img width="1012" height="752" alt="image" src="https://github.com/user-attachments/assets/897f73f0-e42b-44f2-9bf4-d9bbb9d3da84" />


3. Ic-Lora support: You can now add videos to the IC-Lora Video Track, which will be used in the new LTX Director Guide node. The LTX Director Guide node now acts as both the previous Guide node and the original Add Video IC Lora Guide node. You can select which ic loras the video uses on the Guide node (make sure to select it for both Guide nodes, so it applies to both the 1st stage and 2nd upscale stage if you want)<img width="1012" height="752" alt="image" src="https://github.com/user-attachments/assets/6e897e0a-1380-46c4-b3f0-b5c646cdab55" />
<img width="510" height="606" alt="image" src="https://github.com/user-attachments/assets/323675ef-2bd5-4ece-9e3a-7fcfa298c875" />

Also there is a audio toggle on the side bar under IC-Lora Video where you can toggle whether the video output uses the audio from the IC lora video or the audio track

4. There is a new sidebar. You can toggle tracks on or off with the buttons (the eye and speaker).
<img width="1040" height="764" alt="image" src="https://github.com/user-attachments/assets/c9593a30-0d1d-4a1d-8935-1e84e1aa90ce" />

5. Now you can set the start time of the timeline, if you want to only generate part of a timeline. You can either set this by editing the start_second/start_frame widget or by using the controls in the top right.
<img width="1040" height="764" alt="image" src="https://github.com/user-attachments/assets/d0493faf-f13f-4e0f-b729-5c623fe166f6" />


6. You can now save/load timelines as a json file. the controls for this are in the settings menu. will save them as a json file, and can be loaded across workflows and keep all the images/videos/settings within the timeline.
<img width="715" height="446" alt="image" src="https://github.com/user-attachments/assets/3de11771-7bea-41f5-9b0a-478142522a2f" />


7. When you right click an image segment, there is now a "Convert to End frame" setting. This makes it so that the keyframe is added at the end of a segment instead of the beginning (mainly for creating last frames at the end of timelines, but can be used in creative ways as well).

You can convert it back to a regular image segment by right clicking it and clicking "Convert to Start Frame"
<img width="482" height="500" alt="image" src="https://github.com/user-attachments/assets/9abca477-92ac-4778-a12e-f2529c8d99b9" />


8. There are new options on the right click menus, like replace with copied image and copy/paste segments

9. You will also notice the global prompt field has been redesigned. Now it will always show on the bottom, and if you connect a string to the global prompt input then it will update in realtime whatever is in the connected node
<img width="944" height="703" alt="image" src="https://github.com/user-attachments/assets/7788187b-6b34-407f-9a83-adb13e15bba5" />


10.The prompt boxes are also now resizable, you can make them both taller by dragging the handle or the bottom edge of the prompt box. This solves the issue where you had to scroll to see the full prompt

11. This was glitchy at first, but you should be able to scrub through the videos and a preview should update relatively smoothly on the timeline. I think i got it to a point where runs pretty well even with multiple videos are on it, but it might not work on other PC's so let me know if it breaks

12. When right clicking on videos there is a Unlink Media option, this is to seperate the linked audio from the video.
    
Also there is a split at playhead option. This will allow you split (or seperate/cut) both images and videos where the playhead is. The hotkey for this is ctrl+b

<img width="291" height="322" alt="image" src="https://github.com/user-attachments/assets/afc0fc29-ab60-4ad3-8d85-000850f789b8" />



13. Retake Mode: This is a seperate mode that allow you to upload a video and "retake" a certain part of it. You can test it by uploading a video, setting which part of it will be regenerated, add a prompt and hit run. It should "retake" that part of the video smoothly blending in it.
<img width="949" height="697" alt="image" src="https://github.com/user-attachments/assets/463e5be6-06eb-459e-8155-fa6a5ca70c53" />
<img width="910" height="693" alt="image" src="https://github.com/user-attachments/assets/9d638c32-c9e8-4711-96d0-a2ffb80c464b" />



14. Mark selection. You can select a segment or multiple segments and hit the mark selection button to set the in/out (start/end) point of the timeline to that segment. There is also the hotkey x that does this and well as right clicking a segment and clicking mark selection.
<img width="941" height="689" alt="image" src="https://github.com/user-attachments/assets/7a25a80f-2f9c-4356-a90c-698c700251d4" />


15. Multi-select: you can now multi select segments to move them around by holding ctrl and clicking them or by holding shift to make a selection box. You can only move segments though, not edit them.

16. Snapping: Snapping/magnet mode is on by default. this will snap various things on the timeline. It can be toggled by hitting "s" or by clicking the magnet button.
<img width="941" height="689" alt="image" src="https://github.com/user-attachments/assets/11a2502e-7608-4a9c-b649-040b1a88205e" />

And alot more, but this is the main stuff that may have bugs (i think i got most of the bugs out, but let me know if you find anything).

Also if you can think of anything that can be improved let me know!


