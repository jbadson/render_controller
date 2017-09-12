public with sharing class TaskHelper {
    public static final string DIVIDER = '--------Save your notes above this line--------';
    private static Map<String, String> allNotes = new Map<String, String>();
    private static Map<String, User> allUsers = new Map<String, User>();
     
    public static void createUsersLookup (List<Task> newTasks) {
        List<User> users = [Select ID, FirstName, LastName, Name from User];     
        for (User a : users) {
            allUsers.put(a.ID, a);
        }
        System.debug('Size of allUsers is ' + allUsers.size());
    } 
     
    public static void createInteractionEventNotesLookup (List<Task> newTasks) {
     
        //Build parent and child list of all Interaction Events and Interaction Notes
        List <NVMContactWorld__InteractionEventNote__c> conList = New List<NVMContactWorld__InteractionEventNote__c>();
        String combinedNote;
        String guid;
        String newGuid;
        String oldGuid;
     
        List<String> TaskCallGuids = new List<String> ();
        for (Task ss : newTasks) {
            TaskCallGuids .Add (ss.CallObject);
        }
        for(NVMContactWorld__InteractionEvent__c event:
            [Select id, name, NVMContactWorld__Agent__c,
            NVMContactWorld__IndexedCallObjectIdentifier__c,
            (SELECT Name,  CreatedDate, NVMContactWorld__Detail__c
            FROM NVMContactWorld__Interaction_Event_Notes__r)
            From NVMContactWorld__InteractionEvent__c
            WHERE NVMContactWorld__IndexedCallObjectIdentifier__c IN :TaskCallGuids
            ORDER BY NVMContactWorld__TimeStamp__c ASC NULLS FIRST]){
            //System.debug('Outside of loop ' + event.NVMContactWorld__IndexedCallObjectIdentifier__c);
            combinedNote = Null;
            //Loop through child records
            for(NVMContactWorld__InteractionEventNote__c note:event.NVMContactWorld__Interaction_Event_Notes__r){
                //Change ID for real name
                User createdByName = allUsers.get(event.NVMContactWorld__Agent__c);
                newGuid = event.NVMContactWorld__IndexedCallObjectIdentifier__c;
                //System.debug('Debug element ' + note);
                //We need to merge single records into 1
                String noteDetail;
                if (note.NVMContactWorld__Detail__c != Null) {
                    //System.debug('This agent saved no notes');
                    noteDetail = note.NVMContactWorld__Detail__c;
                }
                else {
                    noteDetail = 'This agent saved no notes';
                }
                conList.add(note);
                //Create the actual string
                combinedNote = createdByName.Name + ' | on ' + note.CreatedDate + ' | ' + noteDetail + '\r\n';
                guid = event.NVMContactWorld__IndexedCallObjectIdentifier__c;
                if (allNotes.get(event.NVMContactWorld__IndexedCallObjectIdentifier__c) == Null) {
                    //System.debug('Map not created - create it');
                    allNotes.put(guid, combinedNote);
                }
                else {
                    //System.debug('Map already created - update it');
                    String oldNotes = allNotes.get(event.NVMContactWorld__IndexedCallObjectIdentifier__c);
                    //System.debug('oldNotes is ' + oldNotes);
                    allNotes.put(event.NVMContactWorld__IndexedCallObjectIdentifier__c, oldNotes + ' \r\n' + combinedNote);
                    //System.debug('allNotes is ' + allNotes.values());
                }
            } //end outer for
        }
    }
    public static void processTasks(List<Task> newTasks) {
      
        createUsersLookup (newTasks);
        createInteractionEventNotesLookup (newTasks);
        System.debug('Starting class');
        //Loop through Task records and get GUIDs to query Interaction Events - checking that it is only NVM Tasks
        for (Task ss : newTasks) {
            if (ss.CallType == Null || ss.CallObject == Null) continue;
            //Final call to the built map to populate description
            String oldValue = ss.Description;
            If (ss.Description == Null) {
                ss.Description = '\r\n' + DIVIDER + '\r\n' + allNotes.get(ss.CallObject);
            }
            else if (oldValue.contains(DIVIDER)) {
                Integer thingsToRemove = oldValue.indexOf(DIVIDER);
                System.debug('Remove string after position ' + thingsToRemove);
                System.debug('Previous call notes found');
                ss.Description = oldValue.left(thingsToRemove) + '\r\n' + DIVIDER + '\r\n' + allNotes.get(ss.CallObject);
            }
            else {
                String newValue = oldValue + '\r\n' + DIVIDER + '\r\n' + allNotes.get(ss.CallObject);
                ss.Description = newValue;
            }
        } //end for
    } //end method
} //end class