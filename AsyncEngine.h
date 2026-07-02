#ifndef __ASYNC_ENGINE_H__
#define __ASYNC_ENGINE_H__

#include "include/ComponentBase.h"
#include "include/AddInDefBase.h"
#include "include/IMemoryManager.h"

// pybind11 заголовки
#include <pybind11/embed.h>
#include <pybind11/chrono.h>
#include <pybind11/functional.h>

namespace py = pybind11;

///////////////////////////////////////////////////////////////////////////////
// class AsyncEngine
class AsyncEngine : public IComponentBase
{
public:
    enum Props
    {
        eLastProp = 0     // Always last
    };

    enum Methods
    {
        eMethInitPython = 0,
        eLastMethod     // Always last
    };

    AsyncEngine(void);
    virtual ~AsyncEngine();
    // IInitDoneBase
    virtual bool ADDIN_API Init(void*) override;
    virtual bool ADDIN_API setMemManager(void* mem) override;
    virtual long ADDIN_API GetInfo() override;
    virtual void ADDIN_API Done() override;
    // ILanguageExtenderBase
    virtual bool ADDIN_API RegisterExtensionAs(WCHAR_T**) override;
    virtual long ADDIN_API GetNProps() override;
    virtual long ADDIN_API FindProp(const WCHAR_T* wsPropName) override;
    virtual const WCHAR_T* ADDIN_API GetPropName(long lPropNum, long lPropAlias) override;
    virtual bool ADDIN_API GetPropVal(const long lPropNum, tVariant* pvarPropVal) override;
    virtual bool ADDIN_API SetPropVal(const long lPropNum, tVariant* varPropVal) override;
    virtual bool ADDIN_API IsPropReadable(const long lPropNum) override;
    virtual bool ADDIN_API IsPropWritable(const long lPropNum) override;
    virtual long ADDIN_API GetNMethods() override;
    virtual long ADDIN_API FindMethod(const WCHAR_T* wsMethodName) override;
    virtual const WCHAR_T* ADDIN_API GetMethodName(const long lMethodNum, const long lMethodAlias) override;
    virtual long ADDIN_API GetNParams(const long lMethodNum) override;
    virtual bool ADDIN_API GetParamDefValue(const long lMethodNum, const long lParamNum, tVariant *pvarParamDefValue) override;   
    virtual bool ADDIN_API HasRetVal(const long lMethodNum) override;
    virtual bool ADDIN_API CallAsProc(const long lMethodNum, tVariant* paParams, const long lSizeArray) override;
    virtual bool ADDIN_API CallAsFunc(const long lMethodNum, tVariant* pvarRetValue, tVariant* paParams, const long lSizeArray) override;
    // LocaleBase
    virtual void ADDIN_API SetLocale(const WCHAR_T* loc) override;
    // UserLanguageBase
    virtual void ADDIN_API SetUserInterfaceLanguageCode(const WCHAR_T* lang) override;
    
private:
    // Фоновые потоки и асинхронные уведомления
    void AsyncThreadWorker();
    void OnAsyncResult(const std::wstring& resultStr);

    // Служебные
    void addError(uint32_t wcode, const wchar_t* source, const wchar_t* descriptor, long code);
    long findName(const wchar_t* names[], const wchar_t* name, const uint32_t size) const;


    bool AsyncEngine::InitPython(tVariant* paParams, const long lSizeArray);

    // Интерфейсы связи с платформой 1С
    IAddInDefBase* m_iConnect = nullptr;
    IMemoryManager* m_iMemory = nullptr;

    // Смарт-пойнтеры для управления памятью Python (RAII подход)
    std::unique_ptr<py::scoped_interpreter> m_pyGuard;
    py::module_                             m_pyModule;
    std::unique_ptr<py::gil_scoped_release> m_gilRelease;

    // Поток фонового event loop Python
    std::thread                             m_asyncThread;

    // Память для Py_SetPythonHome должна жить всё время жизни интерпретатора
    std::unique_ptr<wchar_t[]>              m_pythonHomeBuffer;

};
#endif //__ASYNC_ENGINE_H__
