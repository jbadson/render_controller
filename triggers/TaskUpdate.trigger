trigger TaskUpdate on Task (before insert, before update) {
 
if (Trigger.isBefore && (Trigger.isInsert || Trigger.isUpdate)) TaskHelper.processTasks(Trigger.new);
}