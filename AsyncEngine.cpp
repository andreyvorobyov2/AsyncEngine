
#include "stdafx.h"
#include <wchar.h>
#include "AsyncEngine.h"
#include <string>
#include <atomic>
#include <filesystem>
#include <thread>
#include <memory>


static const WCHAR_T g_kClassNames[] = u"AsyncEngine";

// Реестр имен свойств
static const wchar_t* g_PropNames[] = 
{
    nullptr
};

// Реестр имен методов
static const wchar_t* g_MethodNames[] = 
{
    L"InitPython",
	L"SelfTest",
	L"RunPlugin",
	L"SendMessageToPlugin"
};


uint32_t convToShortWchar(WCHAR_T** Dest, const wchar_t* Source);
uint32_t convFromShortWchar(wchar_t** Dest, const WCHAR_T* Source);
uint32_t getLenShortWcharStr(const WCHAR_T* Source);
static AppCapabilities g_capabilities = eAppCapabilitiesInvalid;
static std::u16string s_names(g_kClassNames);

long GetClassObject(const WCHAR_T* wsName, IComponentBase** pInterface)
{
    if(!*pInterface)
    {
        *pInterface= new AsyncEngine();
        return (long)*pInterface;
    }
    return 0;
}

AppCapabilities SetPlatformCapabilities(const AppCapabilities capabilities)
{
    g_capabilities = capabilities;
    return eAppCapabilitiesLast;
}

AttachType GetAttachType() { return eCanAttachAny; }

long DestroyObject(IComponentBase** pIntf)
{
    if(!*pIntf)
        return -1;

    delete *pIntf;
    *pIntf = 0;
    return 0;
}

const WCHAR_T* GetClassNames()
{ 
    return s_names.c_str(); 
}

AsyncEngine::AsyncEngine()
{
    m_iMemory = nullptr;
    m_iConnect = nullptr;
}

AsyncEngine::~AsyncEngine() {}

bool AsyncEngine::Init(void* pConnection) 
{ 
    m_iConnect = (IAddInDefBase*)pConnection;
    return m_iConnect != nullptr;
}

bool AsyncEngine::InitPython(tVariant* paParams, const long lSizeArray) 
{
    if (paParams[0].vt != VTYPE_PWSTR || paParams[1].vt != VTYPE_PWSTR || paParams[2].vt != VTYPE_PWSTR) 
    {
        addError(ADDIN_E_VERY_IMPORTANT, L"AsyncEngine", L"Invalid parameter types. Expected (String, String, String).", 0);
        return false;
    }

    wchar_t* cStrExecutable = nullptr;
    wchar_t* cStrPath = nullptr;
    wchar_t* cStrModule = nullptr;

    // Маршаллинг строк из формата 1С (UTF-16) в системный wchar_t
    convFromShortWchar(&cStrExecutable, (WCHAR_T*)paParams[0].pwstrVal);
    convFromShortWchar(&cStrPath, (WCHAR_T*)paParams[1].pwstrVal);
    convFromShortWchar(&cStrModule, (WCHAR_T*)paParams[2].pwstrVal);

    // RAII контейнеры строк для автоматической очистки
    std::unique_ptr<wchar_t[]> autoExecutable(cStrExecutable);
    std::unique_ptr<wchar_t[]> autoPath(cStrPath);
    std::unique_ptr<wchar_t[]> autoModule(cStrModule);

    std::wstring wstrPath(cStrPath);
    std::wstring wstrModule(cStrModule);

    ::LoadLibraryW(L"python314.dll");

    try 
    {
        // Сохраняем буфер пути PythonHome в компоненте, так как Python не копирует его себе внутри Py_SetPythonHome
        size_t execLen = wcslen(cStrExecutable) + 1;
        m_pythonHomeBuffer = std::make_unique<wchar_t[]>(execLen);
        wcscpy_s(m_pythonHomeBuffer.get(), execLen, cStrExecutable);

        ::Py_SetPythonHome(m_pythonHomeBuffer.get());

        // Инициализация встроенного интерпретатора Python
        m_pyGuard = std::make_unique<py::scoped_interpreter>();

        {
            py::module_ sys = py::module_::import("sys");

            // Конвертация путей в UTF-8 для корректной интеграции с Python модулями
            sys.attr("path").attr("append")(wstrPath);

            std::string utf8Module = std::filesystem::path(wstrModule).u8string();
            m_pyModule = py::module_::import(utf8Module.c_str());
        }

        // Высвобождаем главный GIL для возможности выполнения асинхронных задач в фоне
        m_gilRelease = std::make_unique<py::gil_scoped_release>();

        // Запуск рабочего потока обработки фонового Event Loop
        py::gil_scoped_acquire acquire;
        m_asyncThread = std::thread(&AsyncEngine::AsyncThreadWorker, this);

        {
            py::gil_scoped_release release;
            std::this_thread::sleep_for(std::chrono::milliseconds(50));
        }
    }
    catch (py::error_already_set& e) 
    {
        m_pythonHomeBuffer.reset();
        std::string errStr = e.what();
        std::wstring wErrStr(errStr.begin(), errStr.end());
        addError(ADDIN_E_VERY_IMPORTANT, L"Python Init Error", wErrStr.c_str(), 0);
        return false;
    }

    return true;
}

long AsyncEngine::GetInfo() { return 2000; } // Native API 2.0

void AsyncEngine::Done()
{
    try
    {
        if (m_pyModule)
        {
            {
                py::gil_scoped_acquire acquire;
                try
                {
                    m_pyModule.attr("stop_async_engine")();
                }
                catch (...) {}

                m_pyModule = py::module_(); // Очистка модуля Python
            }

            //if (m_gilRelease) {
				m_gilRelease.reset(); // Возвращаем GIL основному потоку перед деструкцией
            //}

            {
				py::gil_scoped_release join_release;

                if (m_asyncThread.joinable())
                {
                    m_asyncThread.join();
                }

            }

            m_pyGuard.reset(); // Корректное закрытие Python
            m_pythonHomeBuffer.reset();
        }
    }
    catch (...) {}
}

bool AsyncEngine::RegisterExtensionAs(WCHAR_T** wsExtensionName)
{ 
    const wchar_t* wsExtension = L"PythonAsyncExtension";
    size_t iActualSize = ::wcslen(wsExtension) + 1;
    if (m_iMemory && m_iMemory->AllocMemory((void**)wsExtensionName, (unsigned)iActualSize * sizeof(WCHAR_T))) 
    {
        ::convToShortWchar(wsExtensionName, wsExtension);
        return true;
    }
    return false;
}

long AsyncEngine::GetNProps() 
{ 
    return eLastProp; 
}

long AsyncEngine::FindProp(const WCHAR_T* wsPropName) 
{ 
    wchar_t* propName = nullptr;
    ::convFromShortWchar(&propName, wsPropName);
    long plPropNum = findName(g_PropNames, propName, eLastProp);
    delete[] propName;
    return plPropNum;
}

const WCHAR_T* AsyncEngine::GetPropName(long lPropNum, long lPropAlias)
{ 
    if (lPropNum >= eLastProp) 
        return nullptr;

    wchar_t* wsCurrentName = (wchar_t*)g_PropNames[lPropNum];
    WCHAR_T* wsPropName = nullptr;
    size_t iActualSize = wcslen(wsCurrentName) + 1;

    if (m_iMemory && wsCurrentName && m_iMemory->AllocMemory((void**)&wsPropName, (unsigned)iActualSize * sizeof(WCHAR_T))) 
    {
        ::convToShortWchar(&wsPropName, wsCurrentName);
    }
    return wsPropName;
}

bool AsyncEngine::GetPropVal(const long lPropNum, tVariant* pvarPropVal) { return false; }

bool AsyncEngine::SetPropVal(const long lPropNum, tVariant *varPropVal) { return false; }

bool AsyncEngine::IsPropReadable(const long lPropNum) { return false; }

bool AsyncEngine::IsPropWritable(const long lPropNum) { return false; }

long AsyncEngine::GetNMethods() 
{ 
    return eLastMethod; 
}

long AsyncEngine::FindMethod(const WCHAR_T* wsMethodName) 
{ 
    wchar_t* name = nullptr;
    ::convFromShortWchar(&name, wsMethodName);
    long plMethodNum = findName(g_MethodNames, name, eLastMethod);
    delete[] name;
    return plMethodNum;
}

const WCHAR_T* AsyncEngine::GetMethodName(const long lMethodNum, const long lMethodAlias)
{ 
    if (lMethodNum >= eLastMethod) 
        return nullptr;
    wchar_t* wsCurrentName = (wchar_t*)g_MethodNames[lMethodNum];
    WCHAR_T* wsMethodName = nullptr;
    size_t iActualSize = wcslen(wsCurrentName) + 1;

    if (m_iMemory && wsCurrentName && m_iMemory->AllocMemory((void**)&wsMethodName, (unsigned)iActualSize * sizeof(WCHAR_T))) {
        ::convToShortWchar(&wsMethodName, wsCurrentName);
    }
    return wsMethodName;
}

long AsyncEngine::GetNParams(const long lMethodNum)
{
    if (lMethodNum == eMethInitPython) return 3;
	if (lMethodNum == eMethRunPlugin) return 3;
	if (lMethodNum == eMethSendMessageToPlugin) return 2;
    return 0; 
}

bool AsyncEngine::GetParamDefValue(const long lMethodNum, const long lParamNum, tVariant *pvarParamDefValue)
{
    TV_VT(pvarParamDefValue) = VTYPE_EMPTY;
    return false; 
} 

bool AsyncEngine::HasRetVal(const long lMethodNum) { return false; }

bool AsyncEngine::CallAsProc(const long lMethodNum, tVariant* paParams, const long lSizeArray) 
{ 
    switch (lMethodNum) 
    {
        case eMethInitPython: return this->InitPython(paParams, lSizeArray);
		case eMethSelfTest: return this->SelfTest();
		case eMethRunPlugin: return this->RunPlugin(paParams, lSizeArray);
		case eMethSendMessageToPlugin: return this->SendMessageToPlugin(paParams, lSizeArray);
        default: return false;
    }
}

bool AsyncEngine::CallAsFunc(const long lMethodNum, tVariant* pvarRetValue, tVariant* paParams, const long lSizeArray) { return false; }

void AsyncEngine::SetLocale(const WCHAR_T* loc) {}

void ADDIN_API AsyncEngine::SetUserInterfaceLanguageCode(const WCHAR_T * lang) {}

bool AsyncEngine::setMemManager(void* mem)
{ 
    m_iMemory = (IMemoryManager*)mem; 
    return m_iMemory != nullptr;
}

void AsyncEngine::addError(uint32_t wcode, const wchar_t* source, const wchar_t* descriptor, long code) 
{
    if (m_iConnect) 
    {
        WCHAR_T* err = nullptr, * descr = nullptr;
        ::convToShortWchar(&err, source); 
        ::convToShortWchar(&descr, descriptor);
        m_iConnect->AddError(wcode, err, descr, code);
        delete[] err; delete[] descr;
    }
}

long AsyncEngine::findName(const wchar_t* names[], const wchar_t* name, const uint32_t size) const 
{
    for (uint32_t i = 0; i < size; i++) 
    {
        if (!wcscmp(names[i], name)) 
            return i;
    }
    return -1;
}

void AsyncEngine::AsyncThreadWorker() {
    py::gil_scoped_acquire acquire;
    try 
    {
        std::function<void(const std::string& ,const std::string&)> callback =
            [this](const std::string& event, const std::string& data) 
            {
                std::wstring wEvent(event.begin(), event.end());
                
                std::filesystem::path pData = std::filesystem::u8path(data);
                std::wstring wData = pData.wstring();

                this->OnAsyncResult(wEvent, wData);
            };
        m_pyModule.attr("start_async_engine")(callback);
    }
    catch (...) {}
}

void AsyncEngine::OnAsyncResult(const std::wstring& event, const std::wstring& data) {
    if (m_iConnect) 
    {
        WCHAR_T* wSource = nullptr, * wEvent = nullptr, * wData = nullptr;
        ::convToShortWchar(&wSource, L"PythonAsyncExtension");
        ::convToShortWchar(&wEvent, event.c_str());
        ::convToShortWchar(&wData, data.c_str());

        {
            py::gil_scoped_release release;
            m_iConnect->ExternalEvent(wSource, wEvent, wData);
        }

        delete[] wSource; delete[] wEvent; delete[] wData;
    }
}

bool AsyncEngine::RunPlugin(tVariant* paParams, const long lSizeArray)
{
    if (lSizeArray < 3 || paParams[0].vt != VTYPE_PWSTR || paParams[1].vt != VTYPE_PWSTR || paParams[2].vt != VTYPE_PWSTR)
    {
        addError(ADDIN_E_VERY_IMPORTANT, L"AsyncEngine", L"Invalid parameters. Expected (String, String, String).", 0);
        return false;
    }

    wchar_t* cPluginName = nullptr;
    wchar_t* cTaskId = nullptr;
    wchar_t* cParamsJson = nullptr;

    convFromShortWchar(&cPluginName, (WCHAR_T*)paParams[0].pwstrVal);
    convFromShortWchar(&cTaskId, (WCHAR_T*)paParams[1].pwstrVal);
    convFromShortWchar(&cParamsJson, (WCHAR_T*)paParams[2].pwstrVal);

    std::unique_ptr<wchar_t[]> autoPlugin(cPluginName);
    std::unique_ptr<wchar_t[]> autoTask(cTaskId);
    std::unique_ptr<wchar_t[]> autoParams(cParamsJson);

    try
    {
        py::gil_scoped_acquire acquire;

        // Конвертируем в UTF-8 для Python
        std::wstring pyPluginName(cPluginName);
        std::wstring pyTaskId(cTaskId);
        std::wstring pyParamsJson(cParamsJson);

        // Вызываем функцию маршрутизатора в async_core.py
        m_pyModule.attr("run_plugin")(pyPluginName, pyTaskId, pyParamsJson);
    }
    catch (py::error_already_set& e)
    {
        std::string errStr = e.what();
        std::wstring wErrStr(errStr.begin(), errStr.end());
        addError(ADDIN_E_VERY_IMPORTANT, L"Python RunPlugin Error", wErrStr.c_str(), 0);
        return false;
    }
    return true;
}

bool AsyncEngine::SendMessageToPlugin(tVariant* paParams, const long lSizeArray)
{
    if (lSizeArray < 2 || paParams[0].vt != VTYPE_PWSTR || paParams[1].vt != VTYPE_PWSTR)
    {
        addError(ADDIN_E_VERY_IMPORTANT, L"AsyncEngine", L"Invalid parameters. Expected (String, String).", 0);
        return false;
    }

    wchar_t* cTaskId = nullptr;
    wchar_t* cCommandJson = nullptr;

    convFromShortWchar(&cTaskId, (WCHAR_T*)paParams[0].pwstrVal);
    convFromShortWchar(&cCommandJson, (WCHAR_T*)paParams[1].pwstrVal);

    std::unique_ptr<wchar_t[]> autoTask(cTaskId);
    std::unique_ptr<wchar_t[]> autoCommand(cCommandJson);

    try
    {
        py::gil_scoped_acquire acquire;

        std::wstring pyTaskId(cTaskId);
        std::wstring pyCommandJson(cCommandJson);

        // Вызываем функцию маршрутизации в async_core.py
        m_pyModule.attr("send_to_plugin")(pyTaskId, pyCommandJson);
    }
    catch (py::error_already_set& e)
    {
        std::string errStr = e.what();
        std::wstring wErrStr(errStr.begin(), errStr.end());
        addError(ADDIN_E_VERY_IMPORTANT, L"Python SendMessage Error", wErrStr.c_str(), 0);
        return false;
    }
    return true;
}

bool AsyncEngine::SelfTest()
{
    try 
    {
        py::gil_scoped_acquire acquire;
        m_pyModule.attr("self_test")();
    }
    catch (py::error_already_set& e) 
    {
        std::string errStr = e.what();
        std::wstring wErrStr(errStr.begin(), errStr.end());
        addError(ADDIN_E_VERY_IMPORTANT, L"Python SelfTest Error", wErrStr.c_str(), 0);
        return false;
    }
    return true;
}

uint32_t convToShortWchar(WCHAR_T** Dest, const wchar_t* Source)
{
    uint32_t len = ::wcslen(Source) + 1;

    if (!*Dest)
        *Dest = new WCHAR_T[len];

    WCHAR_T* tmpShort = *Dest;
    wchar_t* tmpWChar = (wchar_t*) Source;
    uint32_t res = 0;

    ::memset(*Dest, 0, len * sizeof(WCHAR_T));

    for (; len; --len, ++res, ++tmpWChar, ++tmpShort)
    {
        *tmpShort = (WCHAR_T)*tmpWChar;
    }

    return res;
}

uint32_t convFromShortWchar(wchar_t** Dest, const WCHAR_T* Source)
{
    uint32_t len = getLenShortWcharStr(Source) + 1;

    if (!*Dest)
        *Dest = new wchar_t[len];

    wchar_t* tmpWChar = *Dest;
    WCHAR_T* tmpShort = (WCHAR_T*)Source;
    uint32_t res = 0;

    ::memset(*Dest, 0, len * sizeof(wchar_t));
    for (; len; --len, ++res, ++tmpWChar, ++tmpShort)
    {
        *tmpWChar = (wchar_t)*tmpShort;
    }

    return res;
}

uint32_t getLenShortWcharStr(const WCHAR_T* Source)
{
    uint32_t res = 0;
    WCHAR_T *tmpShort = (WCHAR_T*)Source;

    while (*tmpShort++)
        ++res;

    return res;
}
