   
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
	
	// Читаем JSON с данными от Python-плагина
	ReaderJSON = New JSONReader();
	ReaderJSON.SetString(Data);
	ResultStructure = ReadJSON(ReaderJSON);
	ReaderJSON.Close();

	If StrStartsWith(Event, "web_scrapper:") Then
	   Callback_WebScrapper(Event, Data, ResultStructure);
	ElsIf StrStartsWith(Event, "socketio_server:") Then
		Callback_SocketIOServer(Event, Data, ResultStructure);
	ElsIf StrStartsWith(Event, "socketio_client:") Then	
		Callback_SocketIOClient(Event, Data, ResultStructure);
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
Procedure Callback_WebScrapper(Event, Data, ResultStructure)
	PluginMethod = StrReplace(Event, "web_scrapper:", "");
	
	If PluginMethod = "Success" Then
		ThisObject.Plugin_WebScrapper_Result = ResultStructure.payload;
	ElsIf PluginMethod = "Status" Then
		Status(ResultStructure.payload);
	ElsIf PluginMethod = "Error" Then
		ThisObject.Plugin_WebScrapper_Result =
		StrTemplate("[%1] - Error: %2", CurrentDate(), ResultStructure.payload);
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
			PayloadReader = New JSONReader;
			PayloadReader.SetString(ResultStructure.payload);
			InternalData = ReadJSON(PayloadReader);
			PayloadReader.Close();
		
			ThisObject.SocketIOServer_Log = 
			ThisObject.SocketIOServer_Log + Chars.LF +
			StrTemplate("[%1] - Connected client ID: %2", CurrentDate(), InternalData.sid);
		ElsIf PluginMethod = "ClientDisconnected" Then
			PayloadReader = New JSONReader;
			PayloadReader.SetString(ResultStructure.payload);
			InternalData = ReadJSON(PayloadReader);
			PayloadReader.Close();
		
			ThisObject.SocketIOServer_Log = 
			ThisObject.SocketIOServer_Log + Chars.LF +
			StrTemplate("[%1] - Disconnected client ID: %2", CurrentDate(), InternalData.sid);
		ElsIf PluginMethod = "MessageReceived" Then
			PayloadReader = New JSONReader;
			PayloadReader.SetString(ResultStructure.payload);
			InternalData = ReadJSON(PayloadReader);
			PayloadReader.Close();
			
			ThisObject.SocketIOServer_Log = 
			ThisObject.SocketIOServer_Log + Chars.LF +
			StrTemplate("[%1] - Client %2 send: %3", CurrentDate(), InternalData.sid, InternalData.data);
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
	ThisObject.SocketIOClient_Chat =
	ThisObject.SocketIOClient_Chat + Chars.LF +
	StrTemplate("[%1] - Unhandled event: %2 Data: %3", CurrentDate(), Event, Data);
EndProcedure

#EndRegion

#Region WebScrapper 

&AtClient
Procedure Plugin_WebSrapper(Command)    
	ThisObject.Plugin_WebScrapper_Result = "";
	
	// Параметры для плагина в формате JSON
	RecordJSON = New JSONWriter();
	RecordJSON.SetString();
	ParametersStruct = New Structure("url", "https://jsonplaceholder.typicode.com/posts");
	WriteJSON(RecordJSON, ParametersStruct);
	ParamsJSON = RecordJSON.Close();

	TaskId = String(New UUID()); // Уникальный ID этой сессии скрапинга

	// Вызываем плагин динамически
	// 1 параметр: имя файла в папочке plugins (без .py)
	// 2 параметр: уникальный ID таски
	// 3 параметр: JSON строка параметров
	AsyncEngineComp.RunPlugin("web_scrapper", TaskId, ParamsJSON);

	_DoMessage("Task " + TaskId + " started in background...");
EndProcedure

#EndRegion

#Region SocketIO_Server

&AtClient
Procedure Plugin_SocketIOServer_Start(Command)
	RecordJSON = New JSONWriter();
	RecordJSON.SetString();
	ParametersStruct = New Structure("host, port", ThisObject.SocketIOServer_Host, ThisObject.SocketIOServer_Port);
	WriteJSON(RecordJSON, ParametersStruct);
	ParamsJSON = RecordJSON.Close();
	ThisObject.SocketIOServer_ID = String(New UUID());
	AsyncEngineComp.RunPlugin("socketio_server", ThisObject.SocketIOServer_ID, ParamsJSON);
EndProcedure

&AtClient
Procedure Plugin_SocketIOServer_BroadcastMessage(Command)
	PayloadStruct = New Structure("event, data", "message_from_server", ThisObject.SocketIOServer_BroadcastMessage);
	RecordJSON = New JSONWriter();
	RecordJSON.SetString();
	CmdStruct = New Structure("action, payload", "broadcast", PayloadStruct);
	WriteJSON(RecordJSON, CmdStruct);
	CmdJSON = RecordJSON.Close();
	AsyncEngineComp.SendMessageToPlugin(ThisObject.SocketIOServer_ID, CmdJSON);
EndProcedure

&AtClient
Procedure Plugin_SocketIOServer_Stop(Command)
	RecordJSON = New JSONWriter;
	RecordJSON.SetString();
	CmdStruct = New Structure("action", "stop");
	WriteJSON(RecordJSON, CmdStruct);
	CmdJSON = RecordJSON.Close();
	AsyncEngineComp.SendMessageToPlugin(ThisObject.SocketIOServer_ID, CmdJSON);
EndProcedure

#EndRegion 

#Region SocketIO_Client

&AtClient
Procedure Plugin_SocketIOClient_Connect(Command)
	RecordJSON = New JSONWriter();
	RecordJSON.SetString();
	
	ParametersStruct = New Structure("host, port", 
	ThisObject.SocketIOClient_Host, 
	ThisObject.SocketIOClient_Port);
	
	If ValueIsFilled(ThisObject.SocketIOClient_UserName) Then
		ParametersStruct.Insert("name", ThisObject.SocketIOClient_UserName);	
	EndIf;
	
	WriteJSON(RecordJSON, ParametersStruct);
	ParamsJSON = RecordJSON.Close();
	ThisObject.SockeIOtClient_ID = String(New UUID());
	AsyncEngineComp.RunPlugin("socketio_client", ThisObject.SockeIOtClient_ID, ParamsJSON);
EndProcedure

&AtClient
Procedure Plugin_SocketIOClient_Send(Command)
	RecordJSON = New JSONWriter;
	RecordJSON.SetString();
	CmdStruct = New Structure("action, payload", "send", ThisObject.SocketIOClient_Message);
	WriteJSON(RecordJSON, CmdStruct);
	CmdJSON = RecordJSON.Close();
	AsyncEngineComp.SendMessageToPlugin(ThisObject.SockeIOtClient_ID, CmdJSON);
EndProcedure

&AtClient
Procedure Plugin_SocketIOClient_Disonnect(Command)
	RecordJSON = New JSONWriter;
	RecordJSON.SetString();
	CmdStruct = New Structure("action", "disconnect");
	WriteJSON(RecordJSON, CmdStruct);
	CmdJSON = RecordJSON.Close();
	AsyncEngineComp.SendMessageToPlugin(ThisObject.SockeIOtClient_ID, CmdJSON);
EndProcedure

#EndRegion

Procedure _DoMessage(Msg)
	UserMsg = New UserMessage();
	UserMsg.Text = Msg;
	UserMsg.Message();	
EndProcedure

