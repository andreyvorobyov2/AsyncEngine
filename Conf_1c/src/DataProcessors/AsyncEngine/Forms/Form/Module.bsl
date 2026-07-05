   
&AtClient
Var AsyncEngineComp;

&AtServer
Procedure OnCreateAtServer(Cancel, StandardProcessing)
	ThisObject.SocketIOServer_Host = "127.0.0.1";
	ThisObject.SocketIOServer_Port = 9000;
	ThisObject.SocketIOServer_BroadcastMessage = "Hello from 1C!"; 
	
	ThisObject.SocketIOClient_Host = "127.0.0.1";
	ThisObject.SocketIOClient_Port = 9000;
EndProcedure

&AtClient
Procedure OnOpen(Cancel)
	AsyncEngineExecutable = "C:\Users\andrey\Documents\VNCOM\out\build\x64-Debug\AsyncEngine.dll";
	PythonExecutable = "C:\Users\andrey\AppData\Local\Python\pythoncore-3.14-64";
	PythonPath = "C:\Users\andrey\Documents\VNCOM";
	PythonModule = "async_core"; 
	
	If AttachAddIn(AsyncEngineExecutable, "AddInNative", AddInType.Native) Then
		AsyncEngineComp = New ("AddIn.AddInNative.PythonAsyncExtension");
		Try
			AsyncEngineComp.InitPython(PythonExecutable, PythonPath, PythonModule, "3.14");
		Except
			_DoMessage(ErrorDescription());
		EndTry;
	Else
		_DoMessage("Failed to attach the external component!");
	EndIf;
EndProcedure

&AtClient
Procedure ExternalEvent(Source, Event, Data)
	If Source <> "PythonAsyncExtension" Then 
		Return;
	EndIf;
	
	If Event = "SelfTest" Then
		_DoMessage("Component event -> Source: " + Source + "; Event: " + Event + "; Data: " + Data);	
		Return;	
	EndIf;  
	
	ResultStruct = _ReadJSON(Data);

	If StrStartsWith(Event, "web_scrapper:") Then
	   Callback_WebScrapper(Event, Data, ResultStruct);
	ElsIf StrStartsWith(Event, "socketio_server:") Then
		Callback_SocketIOServer(Event, Data, ResultStruct);
	ElsIf StrStartsWith(Event, "socketio_client:") Then	
		Callback_SocketIOClient(Event, Data, ResultStruct);
	Else
		_DoMessage("Event: " + Event + " Data: " + Data);
	EndIf;
EndProcedure

&AtClient
Procedure SelfTest(Command)    
	If AsyncEngineComp <> Undefined Then
		Try
			AsyncEngineComp.SelfTest();
		Except
			_DoMessage(ErrorDescription());
		EndTry;
	Else
		_DoMessage("External component not attahed!");
	EndIf;
EndProcedure

#Region Callback

&AtClient
Procedure Callback_WebScrapper(Event, Data, ResultStruct)
	PluginMethod = StrReplace(Event, "web_scrapper:", "");
	
	If PluginMethod = "Success" Then
		ThisObject.Plugin_WebScrapper_Result = ResultStruct.payload;
	ElsIf PluginMethod = "Status" Then
		Status(ResultStruct.payload);
	ElsIf PluginMethod = "Error" Then
		ThisObject.Plugin_WebScrapper_Result =
		StrTemplate("[%1] - Error: %2", CurrentDate(), ResultStruct.payload);
	Else                                      
		ThisObject.Plugin_WebScrapper_Result =
		StrTemplate("[%1] - Unhandled event: %2 Data: %3", CurrentDate(), Event, Data);
	EndIf;	
EndProcedure

&AtClient
Procedure Callback_SocketIOServer(Event, Data, ResultStructure)
	PluginMethod = StrReplace(Event, "socketio_server:", "");
		
	If  PluginMethod = "Error" Then
		ThisObject.SocketIOServer_Log = 
		ThisObject.SocketIOServer_Log + Chars.LF +
		StrTemplate("[%1] - Error: %2", CurrentDate(), ResultStructure.payload);
	Else
		
		If PluginMethod = "ServerStarted" Then
			ThisObject.SocketIOServer_Log = 
			ThisObject.SocketIOServer_Log + Chars.LF +
			StrTemplate("[%1] - Success: %2", CurrentDate(), ResultStructure.payload);
		ElsIf PluginMethod = "BroadcastSent" Then
			ThisObject.SocketIOServer_Log = 
			ThisObject.SocketIOServer_Log + Chars.LF +
			StrTemplate("[%1] - Broadcast sent: %2", CurrentDate(), ResultStructure.payload);
		ElsIf PluginMethod = "ClientConnected" Then
			InternalData = _ReadJSON(ResultStructure.payload);
			ThisObject.SocketIOServer_Log = 
			ThisObject.SocketIOServer_Log + Chars.LF +
			StrTemplate("[%1] - Connected client ID: %2", CurrentDate(), InternalData.sid);
		ElsIf PluginMethod = "ClientDisconnected" Then
			InternalData = _ReadJSON(ResultStructure.payload);
			ThisObject.SocketIOServer_Log = 
			ThisObject.SocketIOServer_Log + Chars.LF +
			StrTemplate("[%1] - Disconnected client ID: %2", CurrentDate(), InternalData.sid);
		ElsIf PluginMethod = "MessageReceived" Then
			InternalData = _ReadJSON(ResultStructure.payload);
			ThisObject.SocketIOServer_Log = 
			ThisObject.SocketIOServer_Log + Chars.LF +
			StrTemplate("[%1] - Client %2 (sid:%3) send: %4", CurrentDate(), 
				InternalData.from_name, InternalData.from_sid, InternalData.data);
		ElsIf PluginMethod = "ServerStopped" Then
			ThisObject.SocketIOServer_Log = 
			ThisObject.SocketIOServer_Log + Chars.LF +
			StrTemplate("[%1] - Server stopped.", CurrentDate());
		Else	                                                 
			ThisObject.SocketIOServer_Log =
			ThisObject.SocketIOServer_Log + Chars.LF +
			StrTemplate("[%1] - Unhandled event: %2 Data: %3", CurrentDate(), Event, Data);
		EndIf;
	EndIf;	
EndProcedure

&AtClient
Procedure Callback_SocketIOClient(Event, Data, ResultStructure)
	PluginMethod = StrReplace(Event, "socketio_server:", "");
	//UserListUpdated
	//Connected
	//MessageSent
	ThisObject.SocketIOClient_Chat =
	ThisObject.SocketIOClient_Chat + Chars.LF +
	StrTemplate("[%1] - Unhandled event: %2 Data: %3", CurrentDate(), Event, Data);
EndProcedure

#EndRegion

#Region WebScrapper 

&AtClient
Procedure Plugin_WebSrapper(Command)    
	ThisObject.Plugin_WebScrapper_Result = "";
	CmdStruct = New Structure("url", "https://jsonplaceholder.typicode.com/posts");
	TaskId = String(New UUID());
	AsyncEngineComp.RunPlugin("web_scrapper", TaskId, _WriteJSON(CmdStruct));
	_DoMessage("Task " + TaskId + " started in background...");
EndProcedure

#EndRegion

#Region SocketIO_Server

&AtClient
Procedure Plugin_SocketIOServer_Start(Command)
	CmdStruct = New Structure("host, port", ThisObject.SocketIOServer_Host, ThisObject.SocketIOServer_Port);
	ThisObject.SocketIOServer_ID = String(New UUID());
	AsyncEngineComp.RunPlugin("socketio_server", ThisObject.SocketIOServer_ID, _WriteJSON(CmdStruct));
EndProcedure

&AtClient
Procedure Plugin_SocketIOServer_BroadcastMessage(Command)
	PayloadStruct = New Structure("event, data", "message_from_server", ThisObject.SocketIOServer_BroadcastMessage);
	CmdStruct = New Structure("action, payload", "broadcast", PayloadStruct);
	AsyncEngineComp.SendMessageToPlugin(ThisObject.SocketIOServer_ID, _WriteJSON(CmdStruct));
EndProcedure

&AtClient
Procedure Plugin_SocketIOServer_Stop(Command)
	CmdStruct = New Structure("action", "stop");
	AsyncEngineComp.SendMessageToPlugin(ThisObject.SocketIOServer_ID, _WriteJSON(CmdStruct));
EndProcedure

#EndRegion 

#Region SocketIO_Client

&AtClient
Procedure Plugin_SocketIOClient_Connect(Command)
	CmdStruct = New Structure("host, port", 
	ThisObject.SocketIOClient_Host, 
	ThisObject.SocketIOClient_Port);
	
	If ValueIsFilled(ThisObject.SocketIOClient_UserName) Then
		CmdStruct.Insert("name", ThisObject.SocketIOClient_UserName);	
	EndIf;
	
	ThisObject.SockeIOtClient_ID = String(New UUID());
	AsyncEngineComp.RunPlugin("socketio_client", ThisObject.SockeIOtClient_ID, _WriteJSON(CmdStruct));
EndProcedure

&AtClient
Procedure Plugin_SocketIOClient_Send(Command)
	CmdStruct = New Structure("action, payload", "send", ThisObject.SocketIOClient_Message);
	AsyncEngineComp.SendMessageToPlugin(ThisObject.SockeIOtClient_ID, _WriteJSON(CmdStruct));
EndProcedure

&AtClient
Procedure Plugin_SocketIOClient_Disonnect(Command)
	CmdStruct = New Structure("action", "disconnect");
	AsyncEngineComp.SendMessageToPlugin(ThisObject.SockeIOtClient_ID, _WriteJSON(CmdStruct));
EndProcedure

#EndRegion

&AtClient
Procedure _DoMessage(Msg)
	UserMsg = New UserMessage();
	UserMsg.Text = Msg;
	UserMsg.Message();	
EndProcedure

&AtServerNoContext
Function _WriteJSON(CmdStruct)
	Writer = New JSONWriter();
	Writer.SetString();
	WriteJSON(Writer, CmdStruct);
	Return Writer.Close();
EndFunction
	
&AtServerNoContext
Function _ReadJSON(StrJSON)
	Reader = New JSONReader();
	Reader.SetString(StrJSON);
	Data = ReadJSON(Reader);
	Reader.Close();
	Return Data;
EndFunction
